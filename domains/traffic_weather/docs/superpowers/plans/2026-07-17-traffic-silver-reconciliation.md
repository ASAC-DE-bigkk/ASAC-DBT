# Traffic Silver Reconciliation 구현 계획

> **작업 방식:** `superpowers:subagent-driven-development`와 TDD로 단계별 구현·검토한다.

## 목표

`silver_seoul_traffic_incident`에서 최신 manifest 기준으로 더 이상 publishable하지 않은 lineage를 기존 upsert와 같은 Trino `MERGE` 안에서 원자적으로 retract한다.

## 보존할 계약

- `source_record_id` canonical grain과 idempotency를 유지한다.
- pinned snapshot, latest manifest state, 30분 lookback, event/ingest time을 유지한다.
- 임시 relation은 `views_enabled=false`인 table로 유지한다.
- stale retraction과 upsert를 하나의 `MERGE` statement로 처리한다.
- 별도 `DELETE`, post-hook, full refresh, 수동 삭제는 사용하지 않는다.
- history Silver에서는 non-publishable lineage만 retract한다. 최신 pinned snapshot에 없는 정상 publishable history는 `silver_seoul_traffic_incident_current`의 책임이므로 삭제하지 않는다.
- destructive reconciliation은 `dev` / `iceberg_dev` / Traffic schema에서만 허용한다.
- 기존 Weather/Traffic full Gold selector와 의도적인 cross-domain serving Gold 포트폴리오는 변경하지 않는다.
- 실행·수정·백필은 Traffic 범위와 dev 환경으로 한정한다.

## Task 1: single-MERGE reconciliation TDD

대상 파일:

- `domains/traffic_weather/tests/traffic/test_publishability_reconcile_strategy.py`
- `domains/traffic_weather/tests/traffic/test_current_state_contract.py`
- `domains/traffic_weather/macros/traffic/traffic_publishability_reconcile.sql`
- `domains/traffic_weather/models/traffic/transform/silver/silver_seoul_traffic_incident.sql`

구현 순서:

- [x] custom strategy와 단일 `MERGE` 계약을 먼저 실패 테스트로 고정한다.
- [x] `source_record_id` null/duplicate preflight를 추가한다.
- [x] 최신 SUCCESS·publishable temp row를 upsert source로 만든다.
- [x] target의 stale lineage를 key-only tombstone으로 만든다.
- [x] tombstone delete, changed-row update, new-row insert를 하나의 `MERGE`로 조합한다.
- [x] history/current 책임 분리와 dev-only 실행 가드를 계약 테스트로 고정한다.
- [x] 기존 model select와 incremental 초기 생성 동작이 유지되는지 검증한다.

Targeted test:

```powershell
$env:PYTHONUTF8='1'
python -m pytest domains/traffic_weather/tests/traffic/test_publishability_reconcile_strategy.py domains/traffic_weather/tests/traffic/test_current_state_contract.py -q
```

## Task 2: DBT 범위 검증

- [x] Traffic/Weather Python suite를 실행한다.
- [x] 배포 컨테이너에서 dbt parse와 Traffic Silver compile을 실행한다.
- [x] dev에서 Traffic Silver targeted run/test를 수행한다.
- [x] 기존 stale 11행이 없어지고 grain uniqueness와 publishability test가 통과하는지 확인한다.
- [x] 같은 입력으로 재실행해 idempotency를 확인한다.
- [x] diff에 selector, 타 도메인, secret/cache 변경이 없는지 확인한다.

예정 커밋 범위:

```text
domains/traffic_weather/models/traffic/transform/silver/silver_seoul_traffic_incident.sql
domains/traffic_weather/macros/traffic/traffic_publishability_reconcile.sql
domains/traffic_weather/tests/traffic/test_publishability_reconcile_strategy.py
domains/traffic_weather/tests/traffic/test_current_state_contract.py
domains/traffic_weather/docs/superpowers/plans/2026-07-17-traffic-silver-reconciliation.md
```
