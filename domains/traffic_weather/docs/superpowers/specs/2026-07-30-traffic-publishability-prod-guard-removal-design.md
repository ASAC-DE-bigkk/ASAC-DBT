# Traffic Publishability 환경 가드 제거 설계

## 상태

- 승인일: 2026-07-30
- 승인안: B — `traffic_publishability_reconcile`의 dev 전용 환경 가드 제거
- 변경 저장소: ASAC-DBT
- 변경 경계: Traffic Silver publishability reconcile 매크로와 해당 계약 테스트

## 배경

`silver_seoul_traffic_incident`는 최신 terminal manifest가 `SUCCESS`이면서
`is_publishable=true`인 lineage만 반영하고, 더 이상 publishable하지 않은 기존 행은
하나의 Trino `MERGE`에서 제거한다.

기존 구현은 이 destructive reconciliation을 보호하기 위해
`dev / iceberg_dev / traffic` 조합만 허용했다. Traffic prod bootstrap과 prod Airflow
runtime이 도입된 뒤에도 이 가드가 유지되어, 정상적인
`prod / iceberg / traffic` 실행이 compile 단계에서 항상 실패한다.

## 결정

환경별 target·catalog·schema allowlist를 담당하는
`traffic_publishability_assert_dev_target` 매크로와 reconcile 전략의 호출을 제거한다.
dev와 prod를 포함한 모든 dbt target에서 동일한 publishability reconcile 전략을
사용한다.

다음 안전장치는 그대로 유지한다.

- `unique_key=['source_record_id']` 고정
- temp/target의 `source_record_id` NULL·중복 preflight
- 최신 terminal manifest의 `SUCCESS`·`is_publishable=true` 필터
- stale lineage와 대체 upsert 행의 충돌 방지
- delete·update·insert를 하나의 Trino `MERGE` statement로 처리
- 모델의 30분 lookback과 pinned `traffic_snapshot_dag_run_id`

## 데이터·실패 영향

- prod Traffic Silver는 기존 테이블을 대상으로 stale non-publishable lineage를 삭제하고
  publishable lineage를 upsert할 수 있다.
- 잘못 구성된 target·catalog·schema를 이 매크로 자체가 거부하지 않는다.
- 대신 dbt profile, Airflow prod runtime 격리, 명시적인 schema 환경값이 목적지 선택을
  전적으로 책임진다.
- preflight 또는 manifest 계약이 깨지면 `MERGE` 전에 실패한다.
- 변경은 Weather와 다른 도메인 모델·매크로·selector에 영향을 주지 않는다.

## 검증

1. 계약 테스트가 dev-only guard와 호출의 부재를 요구하도록 먼저 변경하고 RED를 확인한다.
2. 매크로에서 환경 가드와 호출만 제거해 GREEN을 확인한다.
3. Traffic publishability·current-state 관련 targeted Python suite를 실행한다.
4. `DBT_TARGET=prod`에서 Traffic Silver를 compile해 기존 compiler error가 사라지는지
   확인한다.
5. prod runtime에서 실패했던 Traffic Silver Asset run을 재실행하고 Gold→D1까지
   수렴하는지 검증한다.
6. Weather/Traffic 이외 파일 변경이 없는지 diff scope를 확인한다.
