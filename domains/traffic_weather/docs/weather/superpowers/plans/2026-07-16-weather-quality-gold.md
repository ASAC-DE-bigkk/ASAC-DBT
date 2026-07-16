# Weather #231 품질·Cross-domain Gold 5종 구현 계획

> 구현은 TDD 순서로 진행하며 commit·push·PR은 Gate B 이후 별도 수행한다.

## Task 1 — superseded WIP를 새 계약으로 교체

Files:
- Modify `models/weather/transform/gold/_gold.yml`
- Modify `models/weather/README.md`
- Modify `docs/weather/dbt_contracts.md`
- Replace `tests/weather/test_weather_quality_gold_contract.py`

Steps:
1. static contract test를 신규 5개 exact set, 모델 파일, metadata marker, grain, source 경계, docs section을 요구하도록 먼저 작성한다.
2. focused pytest를 실행해 기존 7-model WIP 때문에 RED임을 확인한다.
3. 기존 normal Gold에 추가된 `quality_gold` WIP와 Seven-product 문서 section을 정확히 제거한다.
4. 신규 5종 문서 section과 source contract를 추가해 static test를 GREEN으로 만든다.

## Task 2 — Weather 품질 Gold 2종

Files:
- Create `models/weather/transform/gold/gold_weather_forecast_completeness_by_admin_dong_hourly.sql`
- Create `models/weather/transform/gold/gold_weather_forecast_issue_cycle_coverage_daily.sql`
- Modify `models/weather/transform/gold/_gold.yml`
- Create focused singular tests under `tests/weather/transform/gold/`

Steps:
1. static test가 SQL의 핵심 8개 분모, exact grain, Grid issue history 사용과 bridge v1 guard를 요구하도록 RED를 만든다.
2. completeness 모델을 public Weather Gold의 관측 forecast grain anchor로 구현한다.
3. issue coverage 모델에서 Grid issue/date forecast slot×bridge v1 canonical 425동×핵심 8항목 expected cell을 exact 재구성하고 observed cell을 left join한다.
4. `bridge_version='weather_admin_dong_grid_bridge_v1'`, `canonical_join_eligible=true`, expected/observed/missing cell, forecast slot, mapped admin count, collected/published max를 독립 재구성하는 양방향 singular test를 추가한다.
5. completeness와 issue coverage 모두 Weather collection/publication as-of를 노출한다.
6. focused pytest와 offline dbt parse/compile을 GREEN으로 만든다.

## Task 3 — Culture cross-domain Gold

Files:
- Modify `models/weather/sources.yml`
- Create `models/weather/transform/gold/gold_weather_x_culture_activity_daily.sql`
- Modify `_gold.yml`
- Create singular tests

Steps:
1. culture Gold source declaration과 exact left join/NULL semantics를 static test로 먼저 잠근다.
2. Weather daily anchor와 일별 lineage에 Culture activity를 결합한다.
3. `culture_observation_present`를 추가하고 source row가 있을 때만 count 0을 실제 0으로 인정하며 행 부재는 NULL로 유지한다.
4. Culture upstream Gold의 freshness가 미노출임을 상수 상태와 계약에 기록하고 임의 timestamp를 만들지 않는다.
5. grain uniqueness, Weather anchor row 보존, present-zero/absent-null을 검증한다.

## Task 4 — Transit·Commerce cross-domain Gold

Files:
- Modify `models/weather/sources.yml`
- Create `gold_weather_x_transit_hourly.sql`
- Create `gold_weather_x_commerce_business_exposure_daily.sql`
- Modify `_gold.yml`
- Create singular tests

Steps:
1. transit/commerce source 및 exact grain contract를 RED로 만든다.
2. Weather wide hourly anchor에 Transit을 left join하고 전체 및 bus/subway/parking presence를 분리하며 source 결측을 NULL로 보존한다. Transit freshness 미노출 상태를 명시한다.
3. Weather daily anchor에 Commerce 최신 stock을 `date(latest_collected_at) <= forecast_date` 조건으로 left join하고 presence와 stock as-of 시각을 보존한다.
4. 두 모델의 grain uniqueness, Weather anchor 보존, present-zero/absent-null과 Commerce no-hindsight 조건을 검증한다.

## Task 5 — 통합 검증

1. focused Weather pytest.
2. `dbt deps`, `dbt parse`, 신규 5종 `dbt compile`, scoped `dbt ls`.
3. `git diff --check`, 변경 범위 검사, diff secret scan.
4. Trino를 일시 기동한 뒤 dev에서 신규 5종을 `threads=1`로 순차 run/test.
5. row count, unique grain, NULL/zero, freshness/as-of, source lineage를 Trino final query로 기록하고 Trino를 다시 중지한다.
