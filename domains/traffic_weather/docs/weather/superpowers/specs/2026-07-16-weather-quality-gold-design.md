# Weather #231 품질·Cross-domain Gold 5종 설계

## 목표와 경계

기존 Weather Gold는 유지하고, 현재 계약으로 방어 가능한 신규 모델만 `iceberg_dev.weather`에 5개 추가한다. 단일 Weather 품질 제품 2개와 Culture·Transit·Commerce 결합 제품 3개를 만든다. 타 도메인 모델·스키마는 읽기만 하며 수정하거나 쓰지 않는다.

`gold_weather_forecast_by_admin_dong`은 계속 유일한 Weather 공개 producer다. 신규 5개는 Weather 내부 분석 Gold이며 `public_gold`로 승격하지 않는다. 기존 7개 normal Gold에 임의의 `quality_gold` 메타데이터를 덧붙이던 이전 WIP는 최신 요구사항이 아니므로 제거한다.

## 공통 의미

- 시간대: KST wall-clock timestamp를 그대로 사용한다.
- 공간축: 공개 Weather Gold와 bridge가 stamp한 `admin_dong_code`만 사용한다.
- 핵심 단기예보 항목: `TMP`, `REH`, `WSD`, `POP`, `SKY`, `PTY`, `PCP`, `SNO`의 8개다. `TMN`·`TMX`처럼 특정 시각에만 나오는 항목은 hourly 완전성 분모에 넣지 않는다.
- count의 0은 upstream 행이 실제 존재하며 0으로 집계됐을 때만 보존한다. upstream 행 자체가 없으면 지표는 NULL이고 별도 `*_observation_present`가 false다.
- Cross-domain 테이블은 날씨와 활동의 동시 노출 context다. 손실, 효과, 원인, 예보 정확도를 주장하지 않는다.
- materialization은 Weather 프로젝트의 기존 table 기본값을 따른다.
- 모든 Weather 기반 모델은 가능한 범위에서 `weather_collected_at_max`와 `weather_published_at_max`를 노출한다.
- Culture와 Transit upstream Gold는 ingest/publication 시각을 노출하지 않는다. 두 cross Gold는 이를 추정하지 않고 `external_freshness_status = 'not_exposed_by_upstream_gold'`로 명시한다.

## 모델 계약

### `gold_weather_forecast_completeness_by_admin_dong_hourly`

- Grain: `admin_dong_code × forecast_at`.
- Anchor: `ref('gold_weather_forecast_by_admin_dong')`의 모든 관측 forecast grain.
- 핵심 8개 항목별 존재 여부, 관측 수, 결측 수, coverage ratio와 `complete|partial|missing_core` 상태를 낸다.
- 같은 grain에서 `issued_at` 최소·최대, `collected_at` 최대를 보존한다.
- 이 제품은 관측된 forecast grain의 category 완전성만 측정한다. 통째로 사라진 forecast slot은 이 모델 하나만으로 탐지할 수 없다.

### `gold_weather_forecast_issue_cycle_coverage_daily`

- Grain: `issued_at × forecast_date`.
- Anchor: issue history를 보존하는 `ref('silver_kma_vilage_fcst_grid')`.
- `bridge_weather_admin_dong_grid`의 v1 중 canonical match만 사용해 native grid를 행정동으로 fan-out한다.
- 해당 issue/date의 Grid Silver에서 관측된 distinct forecast slot 집합 × `bridge_version = 'weather_admin_dong_grid_bridge_v1'`이고 `canonical_join_eligible = true`인 distinct 행정동 집합 × 핵심 8개 항목의 exact expected cell 집합을 재구성해 분모로 삼는다.
- observed cell은 Grid Silver core row를 같은 bridge v1에 결합한 distinct `admin_dong_code × forecast_at × category`다. native grid row 수를 행정동 coverage 분자로 사용하지 않는다.
- observed·expected·missing cell 수, 425개 mapped canonical 행정동 수, forecast slot 수, coverage ratio, `weather_collected_at_max`, `weather_published_at_max`와 상태를 낸다.
- 완전히 미수집된 issue/date 자체는 관측할 수 없으며, 이 값은 예보 정확도나 공식 KMA 발행 schedule 준수율이 아니다.

### `gold_weather_x_culture_activity_daily`

- Grain: `admin_dong_code × forecast_date`.
- Weather anchor: `ref('gold_weather_daily_by_admin_dong')`와 공개 Weather Gold의 일별 lineage.
- External source: `culture.gold_culture_activity_by_dong`.
- `culture_observation_present`를 제공한다. 문화 upstream 행이 있으면 실제 0 count를 보존하고, 행이 없으면 활동 count는 NULL이다.
- Culture Gold에는 collection/publication 시각이 없으므로 `external_freshness_status`를 미노출 상태로 고정하고 freshness를 추정하지 않는다.
- 활동은 정밀 행정동에 매핑된 문화 데이터만 포함하며 스포츠는 upstream 계약대로 제외한다.

### `gold_weather_x_transit_hourly`

- Grain: `admin_dong_code × hour_at`.
- Weather anchor: `ref('gold_weather_forecast_wide_by_admin_dong')`.
- External source: `transit.gold_transit_dong_hourly`.
- 버스·지하철·주차 지표를 같은 동·시간에 left join한다. `transit_observation_present`, `bus_observation_present`, `subway_observation_present`, `parking_observation_present`를 별도로 제공한다. source row 부재는 NULL이며 0으로 바꾸지 않는다.
- Transit Gold에는 collection/publication 시각이 없으므로 `external_freshness_status`를 미노출 상태로 고정하고 freshness를 추정하지 않는다.
- 지하철은 소수 행정동만 관측되고 주차 점유율은 upstream 결손일 수 있음을 계약에 남긴다.

### `gold_weather_x_commerce_business_exposure_daily`

- Grain: `admin_dong_code × forecast_date`.
- Weather anchor: `ref('gold_weather_daily_by_admin_dong')`와 일별 lineage.
- External source: `commerce.gold_license_dong_summary`.
- 최신 사업체 stock을 forecast date마다 반복해 날씨 exposure context로 제공한다. `commerce_observation_present`와 `commerce_latest_collected_at`을 반드시 함께 보존한다.
- `date(commerce_latest_collected_at) <= forecast_date`인 경우만 결합해 최신 stock을 과거 forecast 날짜에 소급 적용하는 hindsight leakage를 막는다.
- 업소 수를 매출·피해·날씨 민감도 또는 인과효과로 해석하지 않는다.

## Source 경계

Weather의 `sources.yml`에 아래 physical contract만 추가한다.

- `culture_gold.gold_culture_activity_by_dong` → schema `culture`
- `transit_gold.gold_transit_dong_hourly` → schema `transit`
- `commerce_gold.gold_license_dong_summary` → schema `commerce`

다른 도메인의 YAML이나 SQL은 변경하지 않는다.

## 검증

- Python static contract가 정확한 신규 5종, grain, source/ref 경계, NULL/zero 문구를 잠근다.
- 각 모델의 primary grain uniqueness와 Weather anchor 보존을 singular SQL test로 검증한다.
- issue coverage test는 Grid issue slot×bridge v1 canonical 425동×핵심 8항목 expected cell을 독립 재구성해 모든 count와 ratio를 양방향 비교한다.
- cross-domain NULL/zero test는 present row의 실제 0 보존과 absent row의 NULL을 각각 검증하며 `coalesce(metric, 0)`을 금지한다.
- `dbt deps`, `parse`, `compile`, scoped `ls`를 먼저 실행한다.
- 최종 warehouse write는 dev에서 Trino를 잠깐 올리고 `threads=1`로 신규 5종만 순차 실행·테스트한다.

## Rollback

신규 SQL/YAML/test/docs와 Weather `sources.yml`의 세 source declaration만 되돌리고 신규 relation 5개만 제거한다. 기존 Weather 및 타 도메인 relation은 변경하지 않는다.
