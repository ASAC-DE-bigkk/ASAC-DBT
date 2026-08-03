# Traffic Cross-Domain Gold Implementation Plan

> **2026-08-03 supersession note:** Task 1·2의 `gold_weather_forecast_by_admin_dong` 소비 경계는 prior eligible issue를 잃는 결함 때문에 폐기했습니다. Corrective implementation은 `bridge_weather_admin_dong_grid` + `silver_kma_vilage_fcst_grid` 이력을 직접 사용하고 `weather_w2_grid_winner_order_key`로 Traffic cutoff 이전의 카테고리별 최신 1건을 선택합니다. 이 보정에 한해 `domains/traffic_weather/contracts/traffic_gold_test_cadence.yml`도 수정 범위에 포함합니다.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build two Traffic-owned cross-domain hourly Gold context tables anchored on canonical Traffic current-hourly rows.

**Architecture:** Add two table models beside existing Traffic Gold SQL. Both select every row from `gold_traffic_incident_current_by_admin_dong_hourly`, left join aggregated context, and use explicit metadata/tests to distinguish cross-domain context from the locked Traffic quality product set.

**Tech Stack:** dbt SQL for Trino/Iceberg, dbt YAML model/source metadata, Python pytest static contract tests, dbt singular SQL tests.

## Global Constraints

- Edit only `domains/traffic_weather/models/traffic/**`, `domains/traffic_weather/tests/traffic/**`, `domains/traffic_weather/docs/traffic/**`, and the corrective test-owner entries in `domains/traffic_weather/contracts/traffic_gold_test_cadence.yml`.
- Do not edit Weather, Citydata, Culture, Transit, Commerce, package, root, DAG, env, or package files.
- Do not commit, push, or open a PR.
- Trino is OFF; do not run warehouse `dbt run` or `dbt test`.
- Run focused Python tests RED before model implementation, then GREEN after.
- Run `git diff --check`, scope check, and diff secret-pattern scan.

---

### Task 1: Static Contract Tests

**Files:**
- Modify: `domains/traffic_weather/tests/traffic/test_traffic_quality_gold_contract.py`
- Create: `domains/traffic_weather/tests/traffic/test_cross_domain_gold_contract.py`

**Interfaces:**
- Consumes: existing `models/traffic/transform/gold/*.yml`, `models/traffic/transform/gold/*.sql`, and `models/traffic/sources.yml`.
- Produces: failing Python tests that lock model names, metadata marker, source/ref boundary, no-hindsight predicate, citydata latest-per-area winner, grains, and documentation.

- [ ] **Step 1: Write failing tests**
  - Add `CROSS_DOMAIN_GOLD_PRODUCTS = {...}` to lock the two names.
  - Update physical quality ship-set test so cross-domain models do not break the five Traffic quality product invariant.
  - Add assertions that each new model has `meta.cross_domain_gold: true` and not `traffic_quality_product: true`.
  - Add static SQL assertions for `ref('gold_traffic_incident_current_by_admin_dong_hourly')`, `ref('bridge_weather_admin_dong_grid')`, `ref('silver_kma_vilage_fcst_grid')`, the absence of `ref('asac_seoul', 'gold_weather_forecast_by_admin_dong')`, `issued_at <= traffic.status_observed_at`, `weather_w2_grid_winner_order_key`, `row_number() over ( partition by admin_dong_code, hour_at, area_cd order by event_at desc nulls last, collected_at desc nulls last )`, and `avg(avg_ppltn)`/`max(avg_ppltn)` with no `sum(avg_ppltn)`.
  - Add source YAML assertions for `source('citydata_gold', 'gold_citydata_ppltn_by_time')`, schema env var, and columns.

- [ ] **Step 2: Run RED**
  - Run: `cd domains/traffic_weather && pytest tests/traffic/test_traffic_quality_gold_contract.py tests/traffic/test_cross_domain_gold_contract.py -q`
  - Expected: FAIL because the new SQL/YAML metadata/source files do not exist yet.

### Task 2: Weather Cross-Domain Model

**Files:**
- Create: `domains/traffic_weather/models/traffic/transform/gold/gold_traffic_incident_x_weather_current_hourly.sql`
- Modify: `domains/traffic_weather/models/traffic/transform/gold/_gold.yml`
- Create singular tests under `domains/traffic_weather/tests/traffic/transform/gold/`.

**Interfaces:**
- Consumes: `ref('gold_traffic_incident_current_by_admin_dong_hourly')`, fixed bridge v1 rows from `ref('bridge_weather_admin_dong_grid')`, and history-preserving forecasts from `ref('silver_kma_vilage_fcst_grid')`.
- Produces: one row per Traffic `product_row_id` with weather coverage and pivoted values.

- [ ] **Step 1: Implement SQL**
  - Materialize as table.
  - CTE `traffic` casts canonical row fields.
  - CTE `weather_bridge` selects canonical-eligible fixed bridge v1 rows; `weather_history` retains non-null-issue Grid history.
  - CTE `weather_candidates` filters logical categories in `('tmp', 'pop', 'reh', 'wsd', 'sky', 'pty')`, joins the exact bridge grid/hour, and requires `weather.issued_at <= traffic.status_observed_at` before ranking.
  - CTE `weather_candidates` computes the deterministic rank per Traffic product/category with `weather_w2_grid_winner_order_key`; `latest_weather_category` keeps only `category_row_num = 1`, and `weather_hourly` then counts categories, maxes lineage timestamps, pivots values, and derives `is_precipitating` only when PTY is present.
  - Final select left joins to Traffic and never coalesces weather missing values to zero.

- [ ] **Step 2: Add YAML**
  - Add model metadata in `_gold.yml` with `cross_domain_gold: true`, `traffic_quality_product: false`, grain, and column tests on product key/admin/hour/quality/source fields.

- [ ] **Step 3: Add singular tests**
  - Add grain unique test.
  - Add reconciliation test that counts rows against Traffic and compares preserved Traffic columns.
  - Add missing-weather-null semantics test.

### Task 3: Citydata Crowding Cross-Domain Model

**Files:**
- Create: `domains/traffic_weather/models/traffic/transform/gold/gold_traffic_incident_x_citydata_crowding_current_hourly.sql`
- Modify: `domains/traffic_weather/models/traffic/transform/gold/_gold.yml`
- Modify: `domains/traffic_weather/models/traffic/sources.yml`
- Create singular tests under `domains/traffic_weather/tests/traffic/transform/gold/`.

**Interfaces:**
- Consumes: `ref('gold_traffic_incident_current_by_admin_dong_hourly')`, `source('citydata_gold', 'gold_citydata_ppltn_by_time')`.
- Produces: one row per Traffic `product_row_id` with latest-per-place crowding context.

- [ ] **Step 1: Add source**
  - Append source `citydata_gold` with schema `{{ env_var('SEOUL_CITYDATA_SCHEMA', 'seoul_citydata') }}` and table `gold_citydata_ppltn_by_time`.
  - Declare required columns: `event_at`, `area_cd`, `admin_dong_code`, `avg_ppltn`, `collected_at`.

- [ ] **Step 2: Implement SQL**
  - Materialize as table.
  - CTE `crowding_candidates` left-joinable by exact admin-dong and `date_trunc('hour', event_at) = hour_at`.
  - CTE `latest_place_hour` applies row_number partitioned by `admin_dong_code`, `hour_at`, `area_cd` ordered by `event_at desc nulls last, collected_at desc nulls last`.
  - CTE `crowding_hourly` groups by admin-dong/hour and emits `monitored_place_count`, `avg(avg_ppltn)`, `max(avg_ppltn)`, latest timestamps, and `crowding_observed`.
  - Final select left joins to Traffic and leaves missing metrics null; `crowding_observed` is false when no latest place row exists.

- [ ] **Step 3: Add YAML and singular tests**
  - Add model metadata with `cross_domain_gold: true`, `traffic_quality_product: false`, crowding missing semantics, and column tests.
  - Add grain unique, reconciliation, and no population sum static/SQL semantics coverage where practical.

### Task 4: Verification

**Files:**
- No new files beyond implementation outputs.

**Interfaces:**
- Consumes: all changes.
- Produces: evidence for RED/GREEN, parse/compile/list, diff hygiene, scope, and secret scan.

- [ ] **Step 1: Run GREEN Python tests**
  - Run: `cd domains/traffic_weather && pytest tests/traffic/test_traffic_quality_gold_contract.py tests/traffic/test_cross_domain_gold_contract.py -q`
  - Expected: PASS.

- [ ] **Step 2: Run dbt non-warehouse checks**
  - Run: `cd domains/traffic_weather && dbt parse --profiles-dir .`
  - Run: `cd domains/traffic_weather && dbt ls --select gold_traffic_incident_x_weather_current_hourly gold_traffic_incident_x_citydata_crowding_current_hourly --profiles-dir .`
  - Run `dbt compile` only if the local profile supports compile without warehouse introspection; do not run warehouse dbt tests.

- [ ] **Step 3: Run final hygiene**
  - Run: `git diff --check`
  - Run scope check ensuring changed files start with one of the three allowed prefixes.
  - Run diff secret-pattern scan for common key/token/password patterns.
