# Weather W2 keyed reconciliation 및 검증 분할 설계

## 문제

`gold_weather_forecast_by_admin_dong`의 bounded recovery가 기존 Gold retained row 전체와 wide payload를 reconciliation 입력으로 만들면서 Trino `HashBuilder` OOM을 일으켰다. Gold write를 여러 트랜잭션으로 나누면 canonical grain과 idempotency가 깨질 수 있고, 단순한 window 축소나 query memory 상향은 full-history 계약을 약화한다.

## 쓰기 계약

- canonical grain은 `(admin_dong_code, forecast_at, category)`를 유지한다.
- repair source는 해당 window의 full desired key set과 key-only delete marker만 만든다.
- Gold write는 조건부 단일 `MERGE` 한 번으로 delete/upsert를 원자적으로 처리한다.
- normal run은 affected key만 검증하고 canonical revision 불일치는 fail-closed한다. 자동 full-target restamp는 수행하지 않는다.
- winner 순서, event/ingest time, publishable anchor, no-downgrade, exact lineage 의미는 기존 계약과 동일하다.

## 검증 분할

write는 나누지 않고 사후 검증만 divide-and-conquer한다.

1. expected-row 및 extra-row reconciliation은 6시간 repair window 전체를 검증한다.
2. winner no-downgrade는 canonical grain을 deterministic `xxhash64`로 8개 bucket에 정확히 한 번씩 배정한다.
3. 각 winner bucket은 window와 publishable anchor를 먼저 적용하고, 필요한 winner-order 필드만 `max_by`로 집계한다.
4. wide payload가 실제 Silver Grid 한 행에서 왔는지는 기존 materialized lineage workset과 4개 lineage bucket이 담당한다.
5. 모든 winner·lineage bucket이 통과한 경우에만 recovery checkpoint를 기록한다.

이 분리는 계약을 삭제하지 않고 winner ordering과 exact lineage의 책임을 분리한다. Airflow는 model/test 이름을 소유하지 않고 dbt named selector와 안정적인 invocation identity만 전달한다.

## dev 검증 근거

- checkpoint: `2026-07-14 18:00:00.000000` ~ `23:59:59.999999` KST
- 최초 keyed Gold write: `MERGE (200,175 rows)`
- 동일 입력 재실행: `MERGE (0 rows)`
- Gold 총행수: `2,064,650`, repair window 행수: `200,175`
- winner bucket 0~7: 모두 PASS, 최종 SQL 기준 각 8.36~18.33초
- lineage bucket 0~3: 모두 PASS, 각 13.16~26.75초
- grain unique, expected reconciliation, extra-row contract: 모두 PASS
- winner 검증 중 관측 Trino 컨테이너 사용량: 약 `4.98 GiB / 9 GiB`

## 운영 경계

- dev 전용이며 prod, full refresh, query memory 상향을 사용하지 않는다.
- recovery DAG는 manual-only, `max_active_runs=1`, `trino_heavy` pool 1 slot, dbt `threads=1`을 유지한다.
- maintenance DAG의 orphan cleanup 실패와 normal Traffic transform 문제는 별도 이슈로 취급한다.
