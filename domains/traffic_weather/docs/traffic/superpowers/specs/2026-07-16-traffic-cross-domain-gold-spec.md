# Traffic Cross-Domain Gold Spec

**Issue:** ASAC-DBT #234

**Goal:** Add exactly two Traffic-owned cross-domain Gold tables in schema `traffic`, each preserving the canonical `gold_traffic_incident_current_by_admin_dong_hourly` admin-dong/hour universe and Traffic quality semantics.

**Tables:**
- `gold_traffic_incident_x_weather_current_hourly`
- `gold_traffic_incident_x_citydata_crowding_current_hourly`

**Scope Constraints:**
- Edit only `domains/traffic_weather/models/traffic/**`, `domains/traffic_weather/tests/traffic/**`, and `domains/traffic_weather/docs/traffic/**`.
- Do not edit Weather, Citydata, Culture, Transit, Commerce, package, root, DAG, or env files.
- Do not commit, push, or open a PR.
- Preserve all existing Traffic quality Gold products and do not mark either new model with `traffic_quality_product: true`.

**Functional Contract:**
- Both models anchor on `ref('gold_traffic_incident_current_by_admin_dong_hourly')`.
- Both models emit one row per canonical `admin_dong_code` x `hour_at` traffic row.
- Both models preserve Traffic `quality_state`, `incident_count`, and `has_incident` null semantics exactly.
- Weather joins the public producer with `ref('asac_seoul', 'gold_weather_forecast_by_admin_dong')` by exact `admin_dong_code` and `date_trunc('hour', forecast_at) = hour_at`.
- Weather accepts only `issued_at <= traffic.status_observed_at`.
- Weather pivots numeric `TMP`, `POP`, `REH`, `WSD` from `value_num` and qualitative `SKY`, `PTY` from `qualitative_code`.
- Weather emits category coverage, latest issued/collected timestamps, pivoted values, and nullable `is_precipitating`; missing weather stays null.
- Citydata source lives in `models/traffic/sources.yml` with schema `{{ env_var('SEOUL_CITYDATA_SCHEMA', 'seoul_citydata') }}` and table `gold_citydata_ppltn_by_time`.
- Citydata picks latest row per `admin_dong_code` x hour x `area_cd` ordered by `event_at desc, collected_at desc`, then aggregates to admin-dong/hour.
- Citydata emits monitored place count, average and peak `avg_ppltn`, latest observed/collected timestamps, and an observed flag whose missing semantics are documented.
- Citydata never sums population and never labels crowding as resident or admin-dong total.
- Metadata uses a separate exact `cross_domain_gold` marker.
