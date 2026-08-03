# Traffic Cross-Domain Gold Spec

> **2026-08-03 corrective decision:** Weather의 공개 Gold는 `(admin_dong_code, forecast_at, category)`별 최신 발표분만 보존하므로 Traffic 관측 시각 기준 이전 발표분 fallback을 보장할 수 없습니다. Weather context 경계는 `bridge_weather_admin_dong_grid`와 `silver_kma_vilage_fcst_grid`로 교체하며, 이 결정은 아래의 기존 public-producer 요구사항을 대체합니다.

**Issue:** ASAC-DBT #234

**Goal:** Add exactly two Traffic-owned cross-domain Gold tables in schema `traffic`, each preserving the canonical `gold_traffic_incident_current_by_admin_dong_hourly` admin-dong/hour universe and Traffic quality semantics.

**Tables:**
- `gold_traffic_incident_x_weather_current_hourly`
- `gold_traffic_incident_x_citydata_crowding_current_hourly`

**Scope Constraints:**
- Corrective change는 `domains/traffic_weather/models/traffic/**`, `domains/traffic_weather/tests/traffic/**`, `domains/traffic_weather/docs/traffic/**`, 그리고 test lineage를 고정하는 `domains/traffic_weather/contracts/traffic_gold_test_cadence.yml`만 수정합니다.
- Do not edit Weather, Citydata, Culture, Transit, Commerce, package, root, DAG, or env files.
- Do not commit, push, or open a PR.
- Preserve all existing Traffic quality Gold products and do not mark either new model with `traffic_quality_product: true`.

**Functional Contract:**
- Both models anchor on `ref('gold_traffic_incident_current_by_admin_dong_hourly')`.
- Both models emit one row per canonical `admin_dong_code` x `hour_at` traffic row.
- Both models preserve Traffic `quality_state`, `incident_count`, and `has_incident` null semantics exactly.
- Weather maps exact `admin_dong_code` through `bridge_weather_admin_dong_grid`의 `weather_admin_dong_grid_bridge_v1` and reads issue history from `silver_kma_vilage_fcst_grid` by `(nx, ny)` and `date_trunc('hour', forecast_at) = hour_at`.
- Weather accepts only `issued_at <= traffic.status_observed_at`; a newer future issue never hides an older eligible issue.
- Weather selects exactly one row per Traffic `product_row_id` and logical category with `weather_w2_grid_winner_order_key`, preserving the deterministic Weather winner semantics.
- Weather pivots numeric `TMP`, `POP`, `REH`, `WSD` from `value_num` and qualitative `SKY`, `PTY` from `qualitative_code`.
- Weather emits category coverage, latest issued/collected timestamps, pivoted values, and nullable `is_precipitating`; missing weather stays null.
- Citydata source lives in `models/traffic/sources.yml` with schema `{{ env_var('SEOUL_CITYDATA_SCHEMA', 'seoul_citydata') }}` and table `gold_citydata_ppltn_by_time`.
- Citydata picks latest row per `admin_dong_code` x hour x `area_cd` ordered by `event_at desc, collected_at desc`, then aggregates to admin-dong/hour.
- Citydata emits monitored place count, average and peak `avg_ppltn`, latest observed/collected timestamps, and an observed flag whose missing semantics are documented.
- Citydata never sums population and never labels crowding as resident or admin-dong total.
- Metadata uses a separate exact `cross_domain_gold` marker.
