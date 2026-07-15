# Weather W2 lineage workset 검증 설계

## 문제

과거 Observation 복구의 6시간 창에서 Gold lineage를 검증할 때, Gold 기대 행 계산과 Silver Grid 전체를 한 dbt test CTE에서 반복 조인하면 Trino 2GB per-node 제한을 넘거나 결과 정산 단계가 길게 정체될 수 있다. 이 검증은 복구 성공 조건이므로 생략하거나 표본화할 수 없다.

## 결정

`weather_w2_observation_recovery_lineage_workset` 모델이 창마다 Gold의 현재 유효 행, exact lineage payload, `(source_id, dag_run_id)`의 결정적 순번을 dev Iceberg table로 materialize한다. 이 모델은 `bounded_reconcile`과 dev target에서만 실행되며, 기존 W2 evidence guard와 Gold winner 비교를 그대로 사용한다.

lineage data test는 workset을 읽어 run 순번을 4개 bucket으로 나누고, 각 bucket에서 Silver Grid를 `source_id + selected_dag_run_id`와 Gold 계약상 non-null인 좌표·시간·원천 키로 hash join한다. 그 뒤 bridge/canonical을 포함한 ordered JSON payload 전체를 비교한다. JSON payload는 nullable 값까지 기존 null-safe 비교 의미를 보존한다.

## 실행 순서

각 6시간 window는 다음 순서로 실행한다.

1. `ask_seoul_weather_w2_recovery_window_models` selector가 Observation, Grid, Gold, lineage workset을 dbt graph 순서로 갱신한다.
2. `ask_seoul_weather_w2_recovery_window_contracts` selector가 expected-row 및 extra-row reconciliation을 실행한다.
3. `ask_seoul_weather_w2_recovery_lineage_contract` selector를 bucket `0`부터 `3`까지 직렬 실행한다.
4. 네 bucket이 모두 통과한 경우에만 checkpoint를 기록한다.

모든 window 완료 후 `ask_seoul_weather_w2_recovery_final_contract` selector를 한 번 실행해 전체 publishability를 정산한다.
DAG는 selector와 invocation identity만 전달하며 model/test 이름과 dbt project 경로는 소유하지 않는다.

## 안전 경계

- workset은 `iceberg_dev.weather`의 recovery 전용 검증 산출물이며 prod target이나 normal W1 흐름에서는 생성하지 않는다.
- W1 30분 lookback, Trino 2GB cap, full-refresh 금지, publishable manifest gate는 변경하지 않는다.
- workset의 window marker가 현재 W2 vars와 다르면 lineage test는 해당 산출물을 사용하지 않는다.
- source/run bucket은 검사 범위만 분할할 뿐, 네 bucket 전체가 합쳐져 모든 Gold lineage 행을 검증한다.

## 검증 근거

실제 2026-07-08 18:00–23:59 KST 창에서 workset materialization은 약 43초, lineage bucket `0`~`3`은 각각 약 7~9초에 PASS했다. Trino는 재시작이나 OOM 없이 동작했다.
