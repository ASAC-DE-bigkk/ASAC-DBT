# Weather W2 canonical 계약 실행 주기 분리 설계

## 목적

`gold_weather_forecast_by_admin_dong`의 최신 winner 계약을 제거하지 않으면서,
3시간 주기 canonical 실행이 전체 이력 재집계 때문에 지연되지 않도록 검증 범위를
분리한다.

- 매 canonical 실행에서는 해당 Bronze snapshot이 영향을 준 product grain만 검증한다.
- 매일 09:15 KST에는 전체 이력과 전체 canonical 계약을 검증한다.
- D1 최초 적재와 dev 배포 전에는 일일 audit과 같은 전체 계약을 수동 SQL 실행으로
  한 번 통과시킨다.

## 보존할 기존 의도

- canonical grain은 `(admin_dong_code, forecast_at, category)`이다.
- winner 순서는 `issued_at`, `collected_at`, lineage tie-break 순서이며
  `weather_w2_grid_winner_order_key`를 단일 정의로 재사용한다.
- Bronze manifest의 최신 상태가 `SUCCESS`이고 `is_publishable=true`인 run만 유효하다.
  `COALESCED` run은 replacement run으로 대체된 상태이므로 winner 후보에서 제외한다.
- `missing=0`, `extra=0`, `invalid_actual_bridge=0`만으로는 stale winner를 탐지할 수
  없으므로 latest-record 계약 자체는 유지한다.
- recovery, canonical write, audit가 동시에 Trino heavy query를 실행하지 않도록
  Airflow pool과 실행 가드를 유지한다.

## 선택한 구조

### 1. 매 실행 영향 grain 계약

기존 canonical 계약 selector에는 경량 latest-record 테스트를 둔다.

1. `weather_snapshot_dag_run_id`에 해당하는 Silver Grid 행에서 영향받은
   `(admin_dong_code, forecast_at, category)` 집합을 만든다.
2. 최신 publishable manifest run과 active bridge에 속하는 Silver 후보만 사용한다.
3. 영향 grain에 대해서만 전체 후보의 deterministic winner를 계산한다.
4. 계산된 winner와 Gold의 모든 payload 및 lineage 필드를 비교한다.

snapshot var가 없거나 manifest 최신 상태가 publishable하지 않으면 테스트는
fail-closed 한다. repair 모드에서는 기존 bounded window 및 checkpoint 계약을
그대로 사용한다.

### 2. 일일 전체 계약 audit

전체 이력 latest-record 테스트는 별도 selector로 분리한다. 이 selector는 기존
canonical 계약 9개와 전체 이력 latest-record 테스트를 함께 실행한다.

ASAC-DAG에는 API 호출이나 모델 write가 없는 read-only audit DAG를 추가한다.

- DAG ID: `weather_w2_canonical_contract_audit`
- schedule: 매일 `09:15 Asia/Seoul`
- 동시 실행: `max_active_runs=1`
- resource: 기존 Trino heavy pool 1 slot
- 동작: `dbt deps` 후 전체 canonical audit selector 실행
- 실패: dbt non-zero exit를 Airflow task 실패로 그대로 노출

09:00 Bronze reliability report와 분리하여 보고서 발송을 막지 않고, 15분 뒤에
실행해 정시 report와의 Trino 경합을 줄인다.

### 3. 배포 전 검증

새 audit DAG를 수동으로 직접 트리거하지 않는다. 로컬에서는 동일한 dbt selector를
컨테이너에서 직접 실행하고, 배포 후 첫 scheduled audit을 확인한다. 수동 DAG
검증이 필요해지면 root `scripts/safe-trigger-dag.sh`의 Weather family가 해당 DAG를
인지한 상태에서만 실행한다.

## 데이터 흐름

```text
3시간 Bronze snapshot
  -> canonical model
  -> 영향 grain 계약
  -> 빠른 성공/실패

매일 09:15 KST
  -> read-only canonical contract audit DAG
  -> canonical 9개 기본 계약
  -> 전체 이력 latest-record 계약
  -> Airflow 성공/실패 기록
```

## 실패 처리

- 영향 grain에서 stale/missing/extra winner가 하나라도 발견되면 해당 canonical run을
  실패시킨다.
- 전체 audit 실패는 데이터 write나 D1 export를 수행하지 않고 audit DAG만 실패시킨다.
- Trino OOM 또는 timeout은 성공으로 간주하지 않는다.
- `COALESCED` run이 expected winner로 다시 선택되면 계약 구현 회귀로 취급한다.
- 전체 audit이 실패한 동안 D1 최초 적재와 신규 배포 완료를 선언하지 않는다.

## 검증 기준

### 정적·단위 검증

- 경량 테스트가 `weather_snapshot_dag_run_id`로 영향 grain을 제한한다.
- 경량·전체 테스트가 동일한 winner-order macro를 사용한다.
- 두 테스트 모두 최신 manifest 상태와 publishability를 적용한다.
- routine selector에는 전체 이력 테스트가 포함되지 않는다.
- full selector에는 canonical 10개 의미 계약이 포함된다.
- audit DAG는 API 수집 task와 write 모델을 포함하지 않는다.

### dev 실행 검증

1. 7/9 용신동 잔여 144건을 bounded staged recovery로 복구한다.
2. 영향 grain 계약을 실행해 `0 failures`를 확인한다.
3. 전체 audit selector를 한 번 실행해 canonical 10개 계약 GREEN을 확인한다.
4. audit DAG import 및 task 구성을 확인한다.
5. merge·dev 재배포 후 첫 09:15 scheduled run을 기록한다.

## 작업 범위 밖

- D1 실제 write 또는 publish 실행
- Traffic serving 모델·DAG 신설
- root `.airflowignore` 변경
- 비담당 도메인 코드 변경
- 기존 Bronze reliability report의 recovery/recollect 혼입 false alarm 수정
