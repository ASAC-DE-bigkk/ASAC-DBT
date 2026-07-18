# Traffic Gold Incremental Exact Set Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Traffic Flow Gold 4개만 pinned Flow run 기반 affected-key incremental로 전환하고, Incident current/exact 16개와 coverage 1개는 table exact-set 계약을 유지하며, Gold test cadence를 exact inventory로 고정한다.

**Architecture:** Flow Silver는 이미 `traffic_flow_snapshot_dag_run_id`로 publishable Flow run을 pinning하고 `(link_id, dag_run_id)` incremental ledger를 만든다. Flow Gold는 별도 watermark를 만들지 않고 Silver ledger의 pinned run identity만 changed-scope interface로 사용한다. Current/exact 계열은 plain incremental merge가 stale row를 제거하지 못하므로 table replacement를 유지하고, selector cadence는 tracked inventory와 fresh manifest premerge validator로 관리한다.

**Tech Stack:** dbt Core, dbt-trino, Trino/Iceberg, Jinja SQL macros, Python 3 pytest, YAML selectors/contracts, PowerShell command surface.

## Global Constraints

- 작업 repo: `C:\Users\Dell3571\Desktop\Projects\ask-seoul-worktrees\dbt-257-traffic-gold-incremental`
- 기준 이슈: ASAC-DBT #257
- 기준 branch: `feat/257-traffic-gold-incremental-exact-set`
- 기준 spec: `domains/traffic_weather/docs/traffic/superpowers/specs/2026-07-18-traffic-gold-incremental-exact-set-design.md`
- 설계 결정: Flow history 4개만 affected-key incremental로 전환한다.
- 설계 결정: `gold_traffic_incident_collection_coverage_5m`는 history 후보이나 1차에서는 `materialized='table'`을 유지한다.
- 설계 결정: Incident current/exact 16개는 1차 hotfix에서 `materialized='table'`을 유지한다.
- Flow incremental source of truth: `silver_seoul_traffic_flow`의 `(link_id, dag_run_id)` ledger와 `traffic_flow_snapshot_dag_run_id` var.
- Optional Flow no-op: incremental invocation에서 `traffic_flow_snapshot_dag_run_id`가 비어 있으면 Flow Gold target을 변경하지 않는다.
- Fail-closed: non-empty `traffic_flow_snapshot_dag_run_id`가 전달됐는데 해당 run의 Silver rows가 0개이면 컴파일/실행 전 명시 실패시킨다.
- Iceberg/dbt-trino safety: Flow incremental model은 `views_enabled=false`, `on_table_exists='drop'`을 명시한다.
- Current exact-set safety: plain merge incremental로 Incident current/exact 16개와 coverage 1개를 바꾸지 않는다.
- Selector cadence exact counts: Gate 236, Hourly 256, Full 296을 유지한다.
- Gold test exact inventory: Gold gate 123, hourly extension 20, daily extension 30, full static axes/admin 10을 tracked file로 검증한다.
- Existing full selector: `ask_seoul_traffic_transform_gold`는 backward-compatible full selector로 유지한다.
- Secret safety: `.env`, API key, R2 key, token, password 값은 출력하거나 문서에 적지 않는다.
- Dev safety: 검증은 `dev` target과 dev schema에서 먼저 수행하고 prod full-refresh/drop은 하지 않는다.
- Git safety: 실행자는 사용자 승인 없이 `git commit`, `git push`, PR 생성, destructive git 명령을 실행하지 않는다. 이 계획의 commit step은 승인 후 실행할 명령을 명시한 것이다.

---

## File Map

### Create

- `domains/traffic_weather/macros/traffic/traffic_flow_incremental_scope.sql`
  - Flow Gold 4개가 공통으로 쓰는 changed rows/keys/hours/profile-key macro와 fail-closed pre-hook macro를 제공한다.
- `domains/traffic_weather/contracts/traffic_gold_test_cadence.yml`
  - fresh manifest의 Traffic Gold test tier membership을 exact inventory로 고정한다.
- `domains/traffic_weather/contracts/traffic/scripts/validate_traffic_gold_test_inventory.py`
  - inventory와 manifest를 비교해 missing/extra/duplicate/count mismatch를 실패시킨다.
- `domains/traffic_weather/contracts/traffic/tests/test_validate_traffic_gold_test_inventory.py`
  - inventory validator의 happy path와 실패 경로를 테스트한다.
- `domains/traffic_weather/tests/traffic/test_gold_incremental_contract.py`
  - Flow Gold SQL이 required macro/config/no-op/fail-closed 계약을 갖는지 정적 테스트한다.
- `domains/traffic_weather/tests/traffic/test_gold_materialization_contract.py`
  - Current/exact 16개와 coverage 1개가 table로 남아 있는지 정적 테스트한다.
- `domains/traffic_weather/analyses/traffic/traffic_gold_flow_shadow_parity.sql`
  - old table relation과 shadow incremental relation을 3-cycle에서 비교할 수 있는 dev-only SQL template이다.

### Modify

- `domains/traffic_weather/models/traffic/transform/gold/gold_traffic_flow_link_latest.sql`
  - `link_id` unique-key incremental merge로 전환한다.
- `domains/traffic_weather/models/traffic/transform/gold/gold_traffic_flow_change_latest.sql`
  - `link_id` unique-key incremental merge로 전환하고 changed link 전체 history를 다시 읽는다.
- `domains/traffic_weather/models/traffic/transform/gold/gold_traffic_flow_congestion_hotspots_hourly.sql`
  - `(hour_at, link_id)` unique-key incremental merge로 전환하고 affected hour 전체를 재계산한다.
- `domains/traffic_weather/models/traffic/transform/gold/gold_traffic_flow_link_time_profile.sql`
  - `(link_id, kst_day_of_week, kst_hour)` unique-key incremental merge로 전환하고 affected profile key 전체 history를 재집계한다.
- `domains/traffic_weather/models/traffic/transform/gold/_serving_gold.yml`
  - Flow 4개 generic tests에 tier tag가 필요하면 test-level `config.tags`를 추가한다.
- `domains/traffic_weather/models/traffic/transform/gold/_gold.yml`
  - 기존 Gold generic tests에 inventory tier와 맞는 `config.tags`를 추가한다.
- `domains/traffic_weather/selectors.yml`
  - Gold model/test tier selectors를 추가하고 기존 full selector를 유지한다.
- `domains/traffic_weather/workflows/premerge_gate.py`
  - fresh manifest 생성 vars에 Flow var를 포함하고, inventory validator를 premerge sequence에 추가한다.
- `domains/traffic_weather/workflows/tests/test_premerge_gate.py`
  - premerge command order와 inventory validator invocation을 검증한다.

### Do Not Modify

- `domains/traffic_weather/models/traffic/transform/silver/silver_seoul_traffic_flow.sql`
  - 기존 pinned run + 30분 lookback 의도를 보존한다.
- Incident current/exact 16개 SQL의 materialization semantics
  - stale row deletion 때문에 table exact-set을 유지한다.
- `scripts/deploy.sh`
  - dev/feature smoke 검증에는 사용하지 않는다.

## Implementation Tasks

### Task 1: Flow incremental scope macro contract

**Files:**
- Create: `domains/traffic_weather/macros/traffic/traffic_flow_incremental_scope.sql`
- Test: `domains/traffic_weather/tests/traffic/test_gold_incremental_contract.py`

**Interfaces:**
- Consumes: `ref('silver_seoul_traffic_flow')`, `var('traffic_flow_snapshot_dag_run_id', '')`, `is_incremental()`
- Produces:
  - `traffic_flow_snapshot_dag_run_id_sql_literal() -> quoted SQL literal`
  - `traffic_flow_changed_rows() -> SQL select`
  - `traffic_flow_changed_links() -> SQL select(link_id)`
  - `traffic_flow_changed_hours() -> SQL select(hour_at)`
  - `traffic_flow_changed_profile_keys() -> SQL select(link_id, kst_day_of_week, kst_hour)`
  - `traffic_flow_assert_pinned_incremental_rows() -> pre-hook SQL/empty string`

- [ ] **Step 1: Write failing static tests for macro names and fail-closed contract**

Create `domains/traffic_weather/tests/traffic/test_gold_incremental_contract.py` with this initial content:

```python
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MACRO_PATH = PROJECT_ROOT / "macros" / "traffic" / "traffic_flow_incremental_scope.sql"
GOLD_DIR = PROJECT_ROOT / "models" / "traffic" / "transform" / "gold"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_flow_incremental_scope_macros_exist_and_use_pinned_run() -> None:
    sql = _read(MACRO_PATH)

    for macro_name in (
        "traffic_flow_snapshot_dag_run_id_sql_literal",
        "traffic_flow_changed_rows",
        "traffic_flow_changed_links",
        "traffic_flow_changed_hours",
        "traffic_flow_changed_profile_keys",
        "traffic_flow_assert_pinned_incremental_rows",
    ):
        assert f"macro {macro_name}(" in sql

    assert "var('traffic_flow_snapshot_dag_run_id', '')" in sql
    assert "ref('silver_seoul_traffic_flow')" in sql
    assert "where 1 = 0" in sql
    assert "exceptions.raise_compiler_error" in sql
    assert "no silver_seoul_traffic_flow rows for pinned traffic_flow_snapshot_dag_run_id" in sql


def test_flow_gold_models_use_required_incremental_safety_config() -> None:
    expected_unique_keys = {
        "gold_traffic_flow_link_latest.sql": "unique_key='link_id'",
        "gold_traffic_flow_change_latest.sql": "unique_key='link_id'",
        "gold_traffic_flow_congestion_hotspots_hourly.sql": "unique_key=['hour_at', 'link_id']",
        "gold_traffic_flow_link_time_profile.sql": "unique_key=['link_id', 'kst_day_of_week', 'kst_hour']",
    }

    for filename, unique_key_fragment in expected_unique_keys.items():
        sql = _read(GOLD_DIR / filename).replace('"', "'")
        assert "materialized='incremental'" in sql
        assert "incremental_strategy='merge'" in sql
        assert unique_key_fragment in sql
        assert "on_table_exists='drop'" in sql
        assert "views_enabled=false" in sql
        assert "traffic_flow_assert_pinned_incremental_rows()" in sql


def test_flow_gold_models_use_their_exact_changed_scope_macro() -> None:
    expected = {
        "gold_traffic_flow_link_latest.sql": "traffic_flow_changed_rows()",
        "gold_traffic_flow_change_latest.sql": "traffic_flow_changed_links()",
        "gold_traffic_flow_congestion_hotspots_hourly.sql": "traffic_flow_changed_hours()",
        "gold_traffic_flow_link_time_profile.sql": "traffic_flow_changed_profile_keys()",
    }

    for filename, macro_call in expected.items():
        sql = _read(GOLD_DIR / filename)
        assert macro_call in sql
```

- [ ] **Step 2: Run the new tests and verify they fail because the macro file does not exist yet**

Run:

```powershell
cd domains/traffic_weather
python -m pytest tests/traffic/test_gold_incremental_contract.py -q
```

Expected:

```text
FAILED tests/traffic/test_gold_incremental_contract.py::test_flow_incremental_scope_macros_exist_and_use_pinned_run
```

The failure should mention `traffic_flow_incremental_scope.sql` missing or the expected macro text missing.

- [ ] **Step 3: Create the macro file**

Create `domains/traffic_weather/macros/traffic/traffic_flow_incremental_scope.sql`:

```sql
{% macro traffic_flow_snapshot_dag_run_id_sql_literal() -%}
  {%- set flow_snapshot_dag_run_id = var('traffic_flow_snapshot_dag_run_id', '') or '' -%}
  '{{ flow_snapshot_dag_run_id | replace("'", "''") }}'
{%- endmacro %}

{% macro traffic_flow_changed_rows() -%}
  {%- set flow_snapshot_dag_run_id = var('traffic_flow_snapshot_dag_run_id', '') or '' -%}
  select
      cast(request_id as varchar) as request_id,
      cast(source_id as varchar) as source_id,
      cast(request_params_json as varchar) as request_params_json,
      cast(link_id as varchar) as link_id,
      cast(flow_speed as double) as flow_speed,
      cast(flow_travel_time as double) as flow_travel_time,
      cast(flow_value_quality as varchar) as flow_value_quality,
      cast(observed_at as timestamp(6)) as observed_at,
      cast(raw_object_key as varchar) as raw_object_key,
      cast(payload_hash as varchar) as payload_hash,
      cast(collected_at as timestamp(6)) as collected_at,
      cast(dag_run_id as varchar) as dag_run_id
  from {{ ref('silver_seoul_traffic_flow') }}
  {%- if is_incremental() %}
  where
    {%- if flow_snapshot_dag_run_id == '' %}
      1 = 0
    {%- else %}
      cast(dag_run_id as varchar) = {{ traffic_flow_snapshot_dag_run_id_sql_literal() }}
    {%- endif %}
  {%- endif %}
{%- endmacro %}

{% macro traffic_flow_changed_links() -%}
  select distinct link_id
  from ({{ traffic_flow_changed_rows() }}) as changed_rows
  where link_id is not null
    and trim(link_id) <> ''
{%- endmacro %}

{% macro traffic_flow_changed_hours() -%}
  select distinct
      cast(date_trunc('hour', {{ asac_axes.utc_to_kst('observed_at') }}) as timestamp(6)) as hour_at
  from ({{ traffic_flow_changed_rows() }}) as changed_rows
  where observed_at is not null
{%- endmacro %}

{% macro traffic_flow_changed_profile_keys() -%}
  select distinct
      link_id,
      day_of_week(cast({{ asac_axes.utc_to_kst('observed_at') }} as timestamp(6))) as kst_day_of_week,
      hour(cast({{ asac_axes.utc_to_kst('observed_at') }} as timestamp(6))) as kst_hour
  from ({{ traffic_flow_changed_rows() }}) as changed_rows
  where link_id is not null
    and trim(link_id) <> ''
    and observed_at is not null
{%- endmacro %}

{% macro traffic_flow_assert_pinned_incremental_rows() -%}
  {%- set flow_snapshot_dag_run_id = var('traffic_flow_snapshot_dag_run_id', '') or '' -%}
  {%- if execute and is_incremental() and flow_snapshot_dag_run_id != '' -%}
    {%- set preflight_sql -%}
      select count(*) as pinned_row_count
      from {{ ref('silver_seoul_traffic_flow') }}
      where cast(dag_run_id as varchar) = {{ traffic_flow_snapshot_dag_run_id_sql_literal() }}
    {%- endset -%}
    {%- set result = run_query(preflight_sql) -%}
    {%- set row = result.rows[0] -%}
    {%- if row[0] | int == 0 -%}
      {{ exceptions.raise_compiler_error(
          'no silver_seoul_traffic_flow rows for pinned traffic_flow_snapshot_dag_run_id'
      ) }}
    {%- endif -%}
  {%- endif -%}
  {{ return('') }}
{%- endmacro %}
```

- [ ] **Step 4: Run the macro contract test again**

Run:

```powershell
cd domains/traffic_weather
python -m pytest tests/traffic/test_gold_incremental_contract.py::test_flow_incremental_scope_macros_exist_and_use_pinned_run -q
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Commit this task only after user approval**

Run only after explicit approval:

```powershell
git add domains/traffic_weather/macros/traffic/traffic_flow_incremental_scope.sql domains/traffic_weather/tests/traffic/test_gold_incremental_contract.py
git commit -m "feat(traffic): add Flow Gold incremental scope macros"
```

Expected:

```text
[feat/257-traffic-gold-incremental-exact-set ...] feat(traffic): add Flow Gold incremental scope macros
```

### Task 2: Convert Flow Gold 4 models to affected-key incremental

**Files:**
- Modify: `domains/traffic_weather/models/traffic/transform/gold/gold_traffic_flow_link_latest.sql`
- Modify: `domains/traffic_weather/models/traffic/transform/gold/gold_traffic_flow_change_latest.sql`
- Modify: `domains/traffic_weather/models/traffic/transform/gold/gold_traffic_flow_congestion_hotspots_hourly.sql`
- Modify: `domains/traffic_weather/models/traffic/transform/gold/gold_traffic_flow_link_time_profile.sql`
- Test: `domains/traffic_weather/tests/traffic/test_gold_incremental_contract.py`

**Interfaces:**
- Consumes: Task 1 macros.
- Produces: incremental SQL that is deterministic under normal run, replay, late arrival, and optional Flow no-op.

- [ ] **Step 1: Run model config tests and verify they fail before SQL edits**

Run:

```powershell
cd domains/traffic_weather
python -m pytest tests/traffic/test_gold_incremental_contract.py::test_flow_gold_models_use_required_incremental_safety_config tests/traffic/test_gold_incremental_contract.py::test_flow_gold_models_use_their_exact_changed_scope_macro -q
```

Expected:

```text
FAILED ... test_flow_gold_models_use_required_incremental_safety_config
FAILED ... test_flow_gold_models_use_their_exact_changed_scope_macro
```

- [ ] **Step 2: Replace `gold_traffic_flow_link_latest.sql` with affected-link latest logic**

Use this complete SQL:

```sql
-- Serving Gold: most recently observed TrafficInfo row per road link.
-- Incremental path recalculates only links touched by the pinned Flow run.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key='link_id',
    on_table_exists='drop',
    views_enabled=false,
    pre_hook="{{ traffic_flow_assert_pinned_incremental_rows() }}"
) }}

with changed_rows as (
    {{ traffic_flow_changed_rows() }}
),

changed_links as (
    select distinct link_id
    from changed_rows
    where link_id is not null
      and trim(link_id) <> ''
),

candidate_changed as (
    select
        cast(request_id as varchar) as request_id,
        cast(source_id as varchar) as source_id,
        cast(request_params_json as varchar) as request_params_json,
        cast(link_id as varchar) as link_id,
        cast(flow_speed as double) as flow_speed,
        cast(flow_travel_time as double) as flow_travel_time,
        cast(flow_value_quality as varchar) as flow_value_quality,
        cast(observed_at as timestamp(6)) as observed_at,
        cast(raw_object_key as varchar) as raw_object_key,
        cast(payload_hash as varchar) as payload_hash,
        cast(collected_at as timestamp(6)) as collected_at,
        cast(dag_run_id as varchar) as dag_run_id
    from changed_rows
),

candidate_target as (
    {% if is_incremental() %}
    select
        cast(target.request_id as varchar) as request_id,
        cast(target.source_id as varchar) as source_id,
        cast(null as varchar) as request_params_json,
        cast(target.link_id as varchar) as link_id,
        cast(target.flow_speed as double) as flow_speed,
        cast(target.flow_travel_time as double) as flow_travel_time,
        cast(target.flow_value_quality as varchar) as flow_value_quality,
        cast(target.observed_at_utc as timestamp(6)) as observed_at,
        cast(target.raw_object_key as varchar) as raw_object_key,
        cast(target.payload_hash as varchar) as payload_hash,
        cast(target.collected_at_utc as timestamp(6)) as collected_at,
        cast(target.dag_run_id as varchar) as dag_run_id
    from {{ this }} as target
    inner join changed_links
        on cast(target.link_id as varchar) = changed_links.link_id
    {% else %}
    select
        cast(null as varchar) as request_id,
        cast(null as varchar) as source_id,
        cast(null as varchar) as request_params_json,
        cast(null as varchar) as link_id,
        cast(null as double) as flow_speed,
        cast(null as double) as flow_travel_time,
        cast(null as varchar) as flow_value_quality,
        cast(null as timestamp(6)) as observed_at,
        cast(null as varchar) as raw_object_key,
        cast(null as varchar) as payload_hash,
        cast(null as timestamp(6)) as collected_at,
        cast(null as varchar) as dag_run_id
    where 1 = 0
    {% endif %}
),

ranked as (
    select
        combined.*,
        row_number() over (
            partition by combined.link_id
            order by combined.observed_at desc, combined.raw_object_key desc, combined.request_id desc
        ) as row_num
    from (
        select * from candidate_changed
        union all
        select * from candidate_target
    ) as combined
)

select
    cast(link_id as varchar) as product_row_id,
    cast(link_id as varchar) as link_id,
    cast(source_id as varchar) as source_id,
    cast(flow_speed as double) as flow_speed,
    cast(flow_travel_time as double) as flow_travel_time,
    cast(flow_value_quality as varchar) as flow_value_quality,
    cast(observed_at as timestamp(6)) as observed_at_utc,
    cast({{ asac_axes.utc_to_kst('observed_at') }} as timestamp(6)) as observed_at_kst,
    cast(raw_object_key as varchar) as raw_object_key,
    cast(payload_hash as varchar) as payload_hash,
    cast(request_id as varchar) as request_id,
    cast(collected_at as timestamp(6)) as collected_at_utc,
    cast(dag_run_id as varchar) as dag_run_id
from ranked
where row_num = 1
```

- [ ] **Step 3: Replace `gold_traffic_flow_change_latest.sql` with affected-link full-history comparison**

Use this complete SQL:

```sql
-- Serving Gold: latest per-link speed and travel-time change versus its prior observation.
-- Incremental path recalculates full history only for links touched by the pinned Flow run.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key='link_id',
    on_table_exists='drop',
    views_enabled=false,
    pre_hook="{{ traffic_flow_assert_pinned_incremental_rows() }}"
) }}

with changed_links as (
    {{ traffic_flow_changed_links() }}
),

scoped_history as (
    select flow.*
    from {{ ref('silver_seoul_traffic_flow') }} as flow
    {% if is_incremental() %}
    inner join changed_links
        on cast(flow.link_id as varchar) = changed_links.link_id
    {% endif %}
),

ordered_history as (
    select
        cast(link_id as varchar) as link_id,
        cast(flow_speed as double) as flow_speed,
        cast(flow_travel_time as double) as flow_travel_time,
        cast(flow_value_quality as varchar) as flow_value_quality,
        cast(observed_at as timestamp(6)) as observed_at_utc,
        cast({{ asac_axes.utc_to_kst('observed_at') }} as timestamp(6)) as observed_at_kst,
        cast(raw_object_key as varchar) as raw_object_key,
        cast(payload_hash as varchar) as payload_hash,
        cast(dag_run_id as varchar) as dag_run_id,
        lag(flow_speed) over (
            partition by link_id
            order by observed_at, raw_object_key, request_id
        ) as previous_flow_speed,
        lag(flow_travel_time) over (
            partition by link_id
            order by observed_at, raw_object_key, request_id
        ) as previous_flow_travel_time,
        lag(observed_at) over (
            partition by link_id
            order by observed_at, raw_object_key, request_id
        ) as previous_observed_at_utc,
        row_number() over (
            partition by link_id
            order by observed_at desc, raw_object_key desc, request_id desc
        ) as latest_row_num
    from scoped_history
)

select
    link_id as product_row_id,
    link_id,
    flow_speed,
    flow_travel_time,
    flow_value_quality,
    observed_at_utc,
    observed_at_kst,
    previous_flow_speed,
    previous_flow_travel_time,
    cast({{ asac_axes.utc_to_kst('previous_observed_at_utc') }} as timestamp(6)) as previous_observed_at_kst,
    case
        when flow_speed is not null and previous_flow_speed is not null
            then flow_speed - previous_flow_speed
    end as flow_speed_change,
    case
        when flow_travel_time is not null and previous_flow_travel_time is not null
            then flow_travel_time - previous_flow_travel_time
    end as flow_travel_time_change,
    case
        when previous_observed_at_utc is null then 'no_prior_observation'
        when flow_speed is null or previous_flow_speed is null then 'speed_unavailable'
        when flow_speed < previous_flow_speed then 'speed_decreased'
        when flow_speed > previous_flow_speed then 'speed_increased'
        else 'speed_unchanged'
    end as speed_change_state,
    raw_object_key,
    payload_hash,
    dag_run_id
from ordered_history
where latest_row_num = 1
```

- [ ] **Step 4: Replace `gold_traffic_flow_congestion_hotspots_hourly.sql` with affected-hour recompute**

Use this complete SQL:

```sql
-- Serving Gold: observed low-speed road-link hotspots by KST hour.
-- Incremental path recalculates all link ranks for hours touched by the pinned Flow run.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['hour_at', 'link_id'],
    on_table_exists='drop',
    views_enabled=false,
    pre_hook="{{ traffic_flow_assert_pinned_incremental_rows() }}"
) }}

with changed_hours as (
    {{ traffic_flow_changed_hours() }}
),

flow_history as (
    select
        cast(link_id as varchar) as link_id,
        cast(flow_speed as double) as flow_speed,
        cast(flow_travel_time as double) as flow_travel_time,
        cast(flow_value_quality as varchar) as flow_value_quality,
        cast(observed_at as timestamp(6)) as observed_at_utc,
        cast({{ asac_axes.utc_to_kst('observed_at') }} as timestamp(6)) as observed_at_kst,
        cast(date_trunc('hour', {{ asac_axes.utc_to_kst('observed_at') }}) as timestamp(6)) as hour_at,
        cast(raw_object_key as varchar) as raw_object_key,
        cast(payload_hash as varchar) as payload_hash,
        cast(dag_run_id as varchar) as dag_run_id
    from {{ ref('silver_seoul_traffic_flow') }} as flow
    {% if is_incremental() %}
    inner join changed_hours
        on cast(date_trunc('hour', {{ asac_axes.utc_to_kst('flow.observed_at') }}) as timestamp(6)) = changed_hours.hour_at
    {% endif %}
),

ranked_link_hour as (
    select
        *,
        row_number() over (
            partition by link_id, hour_at
            order by observed_at_utc desc, raw_object_key desc
        ) as link_hour_row_num
    from flow_history
),

latest_link_hour as (
    select *
    from ranked_link_hour
    where link_hour_row_num = 1
),

ranked_hotspots as (
    select
        *,
        rank() over (
            partition by hour_at
            order by flow_speed asc nulls last, link_id asc
        ) as congestion_rank,
        count(*) over (partition by hour_at) as observed_link_count
    from latest_link_hour
)

select
    concat(link_id, '|', to_iso8601(cast(hour_at as timestamp(6)))) as product_row_id,
    link_id,
    hour_at,
    flow_speed,
    flow_travel_time,
    flow_value_quality,
    observed_at_utc,
    observed_at_kst,
    congestion_rank,
    observed_link_count,
    case
        when flow_speed is null then 'missing_speed'
        when congestion_rank <= 10 then 'lowest_speed_top_10'
        else 'observed'
    end as hotspot_state,
    raw_object_key,
    payload_hash,
    dag_run_id
from ranked_hotspots
```

- [ ] **Step 5: Replace `gold_traffic_flow_link_time_profile.sql` with affected-profile recompute**

Use this complete SQL:

```sql
-- Serving Gold: observed TrafficInfo rhythm by road link, KST weekday, and hour.
-- Incremental path recalculates profile cells touched by the pinned Flow run.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['link_id', 'kst_day_of_week', 'kst_hour'],
    on_table_exists='drop',
    views_enabled=false,
    pre_hook="{{ traffic_flow_assert_pinned_incremental_rows() }}"
) }}

with changed_profile_keys as (
    {{ traffic_flow_changed_profile_keys() }}
),

flow_history as (
    select
        cast(flow.link_id as varchar) as link_id,
        cast(flow.flow_speed as double) as flow_speed,
        cast(flow.flow_travel_time as double) as flow_travel_time,
        cast({{ asac_axes.utc_to_kst('flow.observed_at') }} as timestamp(6)) as observed_at_kst,
        day_of_week(cast({{ asac_axes.utc_to_kst('flow.observed_at') }} as timestamp(6))) as kst_day_of_week,
        hour(cast({{ asac_axes.utc_to_kst('flow.observed_at') }} as timestamp(6))) as kst_hour
    from {{ ref('silver_seoul_traffic_flow') }} as flow
    {% if is_incremental() %}
    inner join changed_profile_keys
        on cast(flow.link_id as varchar) = changed_profile_keys.link_id
       and day_of_week(cast({{ asac_axes.utc_to_kst('flow.observed_at') }} as timestamp(6))) = changed_profile_keys.kst_day_of_week
       and hour(cast({{ asac_axes.utc_to_kst('flow.observed_at') }} as timestamp(6))) = changed_profile_keys.kst_hour
    {% endif %}
)

select
    concat(
        link_id, '|',
        cast(kst_day_of_week as varchar), '|',
        cast(kst_hour as varchar)
    ) as product_row_id,
    link_id,
    kst_day_of_week,
    kst_hour,
    count(*) as observation_count,
    count_if(flow_speed is not null) as speed_observation_count,
    round(avg(flow_speed), 2) as avg_flow_speed,
    min(flow_speed) as min_flow_speed,
    max(flow_speed) as max_flow_speed,
    round(avg(flow_travel_time), 2) as avg_flow_travel_time,
    min(observed_at_kst) as first_observed_at_kst,
    max(observed_at_kst) as last_observed_at_kst
from flow_history
group by 1, 2, 3, 4
```

- [ ] **Step 6: Run static Flow Gold contract tests**

Run:

```powershell
cd domains/traffic_weather
python -m pytest tests/traffic/test_gold_incremental_contract.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 7: Parse the four models with both incident and flow vars**

Run:

```powershell
cd domains/traffic_weather
dbt parse --no-partial-parse --target dev --target-path target/flow-gold-parse --vars '{"traffic_snapshot_dag_run_id":"ci__traffic-gold-incremental","traffic_flow_snapshot_dag_run_id":"ci__traffic-gold-incremental","traffic_citydata_crowding_snapshot_id":1}'
```

Expected:

```text
Done.
```

- [ ] **Step 8: Compile the four models with optional Flow no-op vars omitted**

Run:

```powershell
cd domains/traffic_weather
dbt compile --select gold_traffic_flow_link_latest gold_traffic_flow_change_latest gold_traffic_flow_congestion_hotspots_hourly gold_traffic_flow_link_time_profile --target dev --target-path target/flow-gold-compile-no-flow --vars '{"traffic_snapshot_dag_run_id":"ci__traffic-gold-incremental","traffic_citydata_crowding_snapshot_id":1}'
```

Expected:

```text
Completed successfully
```

Then inspect compiled SQL and confirm `where 1 = 0` appears inside each changed-scope CTE for incremental branches when dbt renders incremental SQL against an existing target in dev. If the target does not exist, this command still proves full-refresh compilation remains var-independent.

- [ ] **Step 9: Commit this task only after user approval**

Run only after explicit approval:

```powershell
git add domains/traffic_weather/models/traffic/transform/gold/gold_traffic_flow_link_latest.sql domains/traffic_weather/models/traffic/transform/gold/gold_traffic_flow_change_latest.sql domains/traffic_weather/models/traffic/transform/gold/gold_traffic_flow_congestion_hotspots_hourly.sql domains/traffic_weather/models/traffic/transform/gold/gold_traffic_flow_link_time_profile.sql domains/traffic_weather/tests/traffic/test_gold_incremental_contract.py
git commit -m "feat(traffic): make Flow Gold affected-key incremental"
```

Expected:

```text
[feat/257-traffic-gold-incremental-exact-set ...] feat(traffic): make Flow Gold affected-key incremental
```

### Task 3: Guard Incident current/exact and coverage table materializations

**Files:**
- Create: `domains/traffic_weather/tests/traffic/test_gold_materialization_contract.py`
- Read-only target files verified by test:
  - `domains/traffic_weather/models/traffic/transform/gold/gold_traffic_incident_active_latest.sql`
  - `gold_traffic_incident_clearance_horizon_latest.sql`
  - `gold_traffic_incident_clearance_watchlist.sql`
  - `gold_traffic_incident_current_by_admin_dong_hourly.sql`
  - `gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily.sql`
  - `gold_traffic_incident_spatial_mapping_quality_daily.sql`
  - `gold_traffic_incident_summary.sql`
  - `gold_traffic_incident_type_mix_latest.sql`
  - `gold_traffic_incident_x_citydata_crowding_current_hourly.sql`
  - `gold_traffic_incident_x_citydata_live_context_current.sql`
  - `gold_traffic_incident_x_commerce_business_exposure_current.sql`
  - `gold_traffic_incident_x_culture_activity_daily.sql`
  - `gold_traffic_incident_x_culture_event_schedule_daily.sql`
  - `gold_traffic_incident_x_flow.sql`
  - `gold_traffic_incident_x_transit_hourly.sql`
  - `gold_traffic_incident_x_weather_current_hourly.sql`
  - `gold_traffic_incident_collection_coverage_5m.sql`

**Interfaces:**
- Consumes: existing SQL model files.
- Produces: static regression guard that fails if any protected model becomes incremental.

- [ ] **Step 1: Create failing guard test**

Create `domains/traffic_weather/tests/traffic/test_gold_materialization_contract.py`:

```python
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR = PROJECT_ROOT / "models" / "traffic" / "transform" / "gold"

CURRENT_EXACT_TABLE_MODELS = (
    "gold_traffic_incident_active_latest",
    "gold_traffic_incident_clearance_horizon_latest",
    "gold_traffic_incident_clearance_watchlist",
    "gold_traffic_incident_current_by_admin_dong_hourly",
    "gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily",
    "gold_traffic_incident_spatial_mapping_quality_daily",
    "gold_traffic_incident_summary",
    "gold_traffic_incident_type_mix_latest",
    "gold_traffic_incident_x_citydata_crowding_current_hourly",
    "gold_traffic_incident_x_citydata_live_context_current",
    "gold_traffic_incident_x_commerce_business_exposure_current",
    "gold_traffic_incident_x_culture_activity_daily",
    "gold_traffic_incident_x_culture_event_schedule_daily",
    "gold_traffic_incident_x_flow",
    "gold_traffic_incident_x_transit_hourly",
    "gold_traffic_incident_x_weather_current_hourly",
)

COVERAGE_HISTORY_TABLE_MODELS = (
    "gold_traffic_incident_collection_coverage_5m",
)


def _model_sql(model_name: str) -> str:
    path = GOLD_DIR / f"{model_name}.sql"
    assert path.is_file(), f"missing protected Gold model: {path}"
    return path.read_text(encoding="utf-8").replace('"', "'").lower()


def test_current_exact_gold_models_remain_table_replacements() -> None:
    for model_name in CURRENT_EXACT_TABLE_MODELS:
        sql = _model_sql(model_name)
        assert "materialized='incremental'" not in sql, model_name
        assert "incremental_strategy" not in sql, model_name
        assert "materialized='table'" in sql or "{{ config(" not in sql, model_name


def test_coverage_history_candidate_remains_table_until_manifest_change_interface_exists() -> None:
    for model_name in COVERAGE_HISTORY_TABLE_MODELS:
        sql = _model_sql(model_name)
        assert "materialized='incremental'" not in sql, model_name
        assert "incremental_strategy" not in sql, model_name
        assert "materialized='table'" in sql or "{{ config(" not in sql, model_name
```

- [ ] **Step 2: Run the guard test**

Run:

```powershell
cd domains/traffic_weather
python -m pytest tests/traffic/test_gold_materialization_contract.py -q
```

Expected:

```text
2 passed
```

If this fails, inspect only the named model and do not convert it to incremental in this issue. Restore the table contract through an explicit model `config(materialized='table')` only if the file currently relies on project default table materialization and the test requires explicitness.

- [ ] **Step 3: Commit this task only after user approval**

Run only after explicit approval:

```powershell
git add domains/traffic_weather/tests/traffic/test_gold_materialization_contract.py
git commit -m "test(traffic): guard current Gold exact-set materializations"
```

Expected:

```text
[feat/257-traffic-gold-incremental-exact-set ...] test(traffic): guard current Gold exact-set materializations
```

### Task 4: Build the manifest-native inventory validator skeleton

**Files:**
- Create: `domains/traffic_weather/contracts/traffic/scripts/validate_traffic_gold_test_inventory.py`
- Create: `domains/traffic_weather/contracts/traffic/tests/test_validate_traffic_gold_test_inventory.py`

**Interfaces:**
- Consumes: dbt `manifest.json`, tracked inventory YAML.
- Produces: generator/validator CLI. Generation derives candidate records from a fresh manifest; validation checks `unique_id`, `path`, `test_type`, the exact sorted non-empty `owner_unique_ids`, tier tags, portfolio counts, cadence totals, and selector counts. Singular reconciliation tests may depend on multiple models, so ownership is never collapsed to one arbitrary node.

- [ ] **Step 1: Create validator tests first**

Create `domains/traffic_weather/contracts/traffic/tests/test_validate_traffic_gold_test_inventory.py`:

```python
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    PROJECT_ROOT
    / "contracts"
    / "traffic"
    / "scripts"
    / "validate_traffic_gold_test_inventory.py"
)


def _test_node(unique_id: str, *, path: str, tags: list[str], owner_unique_id: str, generic: bool = False) -> dict[str, object]:
    node = {
        "unique_id": unique_id,
        "resource_type": "test",
        "name": unique_id.rsplit(".", 1)[-1],
        "original_file_path": path,
        "tags": tags,
        "depends_on": {"nodes": [owner_unique_id]},
    }
    if generic:
        node["test_metadata"] = {"name": "not_null"}
    return node


def _portfolio_test_nodes() -> dict[str, dict[str, object]]:
    nodes: dict[str, dict[str, object]] = {}

    def add_group(prefix: str, count: int, tag: str, owner_unique_id: str, *, inventory_tier: str | None = None) -> None:
        for index in range(1, count + 1):
            unique_id = f"test.asac_seoul.{prefix}_{index:03d}"
            path = f"tests/traffic/transform/{prefix}/{prefix}_{index:03d}.sql"
            nodes[unique_id] = _test_node(
                unique_id,
                path=path,
                tags=[tag],
                owner_unique_id=owner_unique_id,
                generic=inventory_tier in {"gate", "hourly_extension", "daily_extension"},
            )

    add_group("availability", 1, "ask_seoul_traffic_transform_availability", "model.asac_seoul.gold_traffic_incident_summary")
    add_group("bronze_source", 70, "ask_seoul_traffic_transform_source", "model.asac_seoul.bronze_seoul_traffic_incident")
    add_group("silver", 42, "ask_seoul_traffic_transform_silver", "model.asac_seoul.silver_seoul_traffic_incident")
    add_group("gold_gate", 123, "traffic_gold_gate", "model.asac_seoul.gold_traffic_incident_summary", inventory_tier="gate")
    add_group("gold_hourly", 20, "traffic_gold_hourly_extension", "model.asac_seoul.gold_traffic_incident_summary", inventory_tier="hourly_extension")
    add_group("gold_daily", 30, "traffic_gold_daily_extension", "model.asac_seoul.gold_traffic_incident_summary", inventory_tier="daily_extension")

    for index in range(1, 8):
        unique_id = f"test.asac_axes.axes_static_{index:03d}"
        nodes[unique_id] = _test_node(
            unique_id,
            path=f"tests/asac_axes/axes_static_{index:03d}.sql",
            tags=["ask_seoul_traffic_transform_asac_axes_contract"],
            owner_unique_id="seed.asac_axes.asac_axes_calendar",
        )
    for index in range(1, 4):
        unique_id = f"test.asac_seoul.admin_static_{index:03d}"
        nodes[unique_id] = _test_node(
            unique_id,
            path=f"tests/common_admin/admin_static_{index:03d}.sql",
            tags=["ask_seoul_traffic_transform_common_admin"],
            owner_unique_id="seed.asac_seoul.common_admin_dong",
        )
    return nodes


def _manifest() -> dict[str, object]:
    return {
        "metadata": {"project_name": "asac_seoul"},
        "nodes": _portfolio_test_nodes(),
    }


def _inventory() -> dict[str, object]:
    manifest = _manifest()
    tests = []
    tier_by_tag = {
        "traffic_gold_gate": "gate",
        "traffic_gold_hourly_extension": "hourly_extension",
        "traffic_gold_daily_extension": "daily_extension",
        "ask_seoul_traffic_transform_asac_axes_contract": "full_static",
        "ask_seoul_traffic_transform_common_admin": "full_static",
    }
    for unique_id, node in sorted(manifest["nodes"].items()):
        tags = set(node["tags"])
        tier_tag = next((tag for tag in tier_by_tag if tag in tags), None)
        if tier_tag is None:
            continue
        tests.append(
            {
                "unique_id": unique_id,
                "path": node["original_file_path"],
                "test_type": "generic" if "test_metadata" in node else "singular",
                "owner_unique_ids": sorted(node["depends_on"]["nodes"]),
                "tier": tier_by_tag[tier_tag],
                "tier_tag": tier_tag,
            }
        )
    return {
        "version": 1,
        "tiers": {
            "gate": {"expected_count": 123},
            "hourly_extension": {"expected_count": 20},
            "daily_extension": {"expected_count": 30},
            "full_static": {"expected_count": 10},
        },
        "total_expected": {
            "gold_gate": 123,
            "gold_hourly": 143,
            "gold_full": 173,
            "traffic_gate": 236,
            "traffic_hourly": 256,
            "traffic_full": 296,
        },
        "tests": tests,
    }


@pytest.fixture
def validator():
    from contracts.traffic.scripts import validate_traffic_gold_test_inventory as module

    return module


def test_valid_inventory_matches_manifest(validator) -> None:
    validator.validate_inventory(
        _manifest(),
        _inventory(),
        selector_counts={
            "ask_seoul_traffic_transform_gold_gate_tests": 123,
            "ask_seoul_traffic_transform_gold_hourly_tests": 143,
            "ask_seoul_traffic_transform_gold_full_tests": 173,
        },
    )


def test_missing_manifest_test_fails(validator) -> None:
    manifest = _manifest()
    del manifest["nodes"]["test.asac_seoul.gold_daily_001"]
    with pytest.raises(validator.InventoryError, match="missing.*gold_daily_001"):
        validator.validate_inventory(manifest, _inventory())


def test_extra_manifest_test_fails(validator) -> None:
    manifest = _manifest()
    manifest["nodes"]["test.asac_seoul.unclassified"] = _test_node(
        "test.asac_seoul.unclassified",
        path="tests/traffic/transform/gold/unclassified.sql",
        tags=["traffic_gold_gate"],
        owner_unique_id="model.asac_seoul.gold_traffic_incident_summary",
    )
    with pytest.raises(validator.InventoryError, match="extra.*unclassified"):
        validator.validate_inventory(manifest, _inventory())


def test_duplicate_inventory_unique_id_fails(validator) -> None:
    inventory = _inventory()
    inventory["tests"].append(dict(inventory["tests"][0]))

    with pytest.raises(validator.InventoryError, match="duplicate.*gold_gate_001"):
        validator.validate_inventory(_manifest(), inventory)


def test_cli_reports_pass(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    inventory_path = tmp_path / "inventory.yml"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")

    import yaml

    inventory_path.write_text(yaml.safe_dump(_inventory(), sort_keys=False), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest_path),
            "--inventory",
            str(inventory_path),
            "--selector-count",
            "ask_seoul_traffic_transform_gold_gate_tests=123",
            "--selector-count",
            "ask_seoul_traffic_transform_gold_hourly_tests=143",
            "--selector-count",
            "ask_seoul_traffic_transform_gold_full_tests=173",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "PASS" in result.stdout
    assert result.stderr == ""
```

- [ ] **Step 2: Run validator tests and verify they fail because script is missing**

Run:

```powershell
cd domains/traffic_weather
python -m pytest contracts/traffic/tests/test_validate_traffic_gold_test_inventory.py -q
```

Expected:

```text
FAILED ... ModuleNotFoundError
```

- [ ] **Step 3: Create the validator script**

Create `domains/traffic_weather/contracts/traffic/scripts/validate_traffic_gold_test_inventory.py`:

```python
#!/usr/bin/env python3
"""Validate Traffic Gold test cadence inventory against a fresh dbt manifest."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Mapping, Sequence

import yaml


VALID_TIERS = ("gate", "hourly_extension", "daily_extension", "full_static")
GOLD_TIER_TAGS = {
    "gate": "traffic_gold_gate",
    "hourly_extension": "traffic_gold_hourly_extension",
    "daily_extension": "traffic_gold_daily_extension",
}
STATIC_TIER_TAGS = {
    "ask_seoul_traffic_transform_asac_axes_contract",
    "ask_seoul_traffic_transform_common_admin",
}
EXPECTED_STATIC_TAG_COUNTS = {
    "ask_seoul_traffic_transform_asac_axes_contract": 7,
    "ask_seoul_traffic_transform_common_admin": 3,
}
PORTFOLIO_GROUP_TAGS = {
    "availability": {"ask_seoul_traffic_transform_availability"},
    "bronze_source": {"ask_seoul_traffic_transform_source"},
    "silver": {"ask_seoul_traffic_transform_silver"},
    "gold_gate": {"traffic_gold_gate"},
    "gold_hourly_extension": {"traffic_gold_hourly_extension"},
    "gold_daily_extension": {"traffic_gold_daily_extension"},
    "full_static": STATIC_TIER_TAGS,
}
EXPECTED_PORTFOLIO_COUNTS = {
    "availability": 1,
    "bronze_source": 70,
    "silver": 42,
    "gold_gate": 123,
    "gold_hourly_extension": 20,
    "gold_daily_extension": 30,
    "full_static": 10,
}
EXPECTED_SELECTOR_COUNTS = {
    "ask_seoul_traffic_transform_gold_gate_tests": 123,
    "ask_seoul_traffic_transform_gold_hourly_tests": 143,
    "ask_seoul_traffic_transform_gold_full_tests": 173,
}


class InventoryError(ValueError):
    """Raised when the Traffic Gold cadence inventory is not exact."""


def _mapping(value: object, label: str) -> Mapping[object, object]:
    if not isinstance(value, Mapping):
        raise InventoryError(f"{label}: expected mapping")
    return value


def _inventory_entries(inventory: Mapping[object, object]) -> list[Mapping[object, object]]:
    tests = inventory.get("tests")
    if not isinstance(tests, list) or not tests:
        raise InventoryError("inventory tests: expected non-empty list")
    entries: list[Mapping[object, object]] = []
    for item in tests:
        entries.append(_mapping(item, "inventory test entry"))
    return entries


def _manifest_test_records(manifest: Mapping[object, object]) -> dict[str, dict[str, object]]:
    nodes = _mapping(manifest.get("nodes"), "manifest.nodes")
    selected: dict[str, dict[str, object]] = {}
    for unique_id, node in nodes.items():
        if not isinstance(unique_id, str) or not isinstance(node, Mapping):
            continue
        if node.get("resource_type") != "test":
            continue
        tags = {str(tag) for tag in node.get("tags", [])}
        path = str(node.get("original_file_path", "")).replace("\\", "/")
        gold_tiers = [tier for tier, tag in GOLD_TIER_TAGS.items() if tag in tags]
        is_full_static = bool(tags & STATIC_TIER_TAGS)
        if len(gold_tiers) > 1 or (gold_tiers and is_full_static):
            raise InventoryError(f"{unique_id}: test belongs to multiple minimum tiers")
        if not gold_tiers and not is_full_static:
            continue
        tier = gold_tiers[0] if gold_tiers else "full_static"
        owner_unique_ids = sorted(
            str(dependency)
            for dependency in _mapping(node.get("depends_on"), f"{unique_id}.depends_on").get("nodes", [])
            if str(dependency).startswith(("model.", "seed."))
        )
        selected[unique_id] = {
            "unique_id": unique_id,
            "path": path,
            "test_type": "generic" if isinstance(node.get("test_metadata"), Mapping) else "singular",
            "owner_unique_ids": owner_unique_ids,
            "tier": tier,
            "tags": tags,
        }
    return selected


def validate_inventory(
    manifest: object,
    inventory: object,
    *,
    selector_counts: Mapping[str, int] | None = None,
) -> None:
    manifest_doc = _mapping(manifest, "manifest")
    inventory_doc = _mapping(inventory, "inventory")
    entries = _inventory_entries(inventory_doc)

    ids: list[str] = []
    tiers: Counter[str] = Counter()
    for entry in entries:
        unique_id = entry.get("unique_id")
        tier = entry.get("tier")
        owner_unique_ids = entry.get("owner_unique_ids")
        if not isinstance(unique_id, str) or not unique_id:
            raise InventoryError("inventory test entry unique_id: expected non-empty string")
        if tier not in VALID_TIERS:
            raise InventoryError(f"{unique_id}: invalid tier {tier!r}")
        if (
            not isinstance(owner_unique_ids, list)
            or not owner_unique_ids
            or any(not isinstance(owner, str) or not owner for owner in owner_unique_ids)
        ):
            raise InventoryError(f"{unique_id}: owner_unique_ids must be a non-empty string list")
        ids.append(unique_id)
        tiers[str(tier)] += 1

    duplicates = sorted(unique_id for unique_id, count in Counter(ids).items() if count != 1)
    if duplicates:
        raise InventoryError(f"duplicate inventory unique_id values: {duplicates}")

    tier_config = _mapping(inventory_doc.get("tiers"), "inventory.tiers")
    for tier in VALID_TIERS:
        config = _mapping(tier_config.get(tier), f"inventory.tiers.{tier}")
        expected_count = config.get("expected_count")
        if tiers[tier] != expected_count:
            raise InventoryError(
                f"tier {tier}: expected_count {expected_count!r}, actual inventory count {tiers[tier]}"
            )

    expected_ids = set(ids)
    actual_records = _manifest_test_records(manifest_doc)
    actual_ids = set(actual_records)
    missing = sorted(expected_ids - actual_ids)
    extra = sorted(actual_ids - expected_ids)
    if missing:
        raise InventoryError(f"missing manifest tests from inventory comparison: {missing}")
    if extra:
        raise InventoryError(f"extra manifest tests not classified by inventory: {extra}")

    for entry in entries:
        unique_id = str(entry["unique_id"])
        actual = actual_records[unique_id]
        expected_path = entry.get("path")
        expected_type = entry.get("test_type")
        expected_owners = sorted(str(owner) for owner in entry.get("owner_unique_ids", []))
        expected_tier = entry.get("tier")
        expected_tier_tag = entry.get("tier_tag")
        if actual["path"] != expected_path:
            raise InventoryError(f"{unique_id}: path mismatch")
        if actual["test_type"] != expected_type:
            raise InventoryError(f"{unique_id}: test_type mismatch")
        if expected_owners != actual["owner_unique_ids"]:
            raise InventoryError(f"{unique_id}: owner_unique_ids mismatch")
        if actual["tier"] != expected_tier:
            raise InventoryError(f"{unique_id}: tier tag mismatch")
        if expected_tier_tag not in actual["tags"]:
            raise InventoryError(f"{unique_id}: required tier_tag mismatch")

    total_expected = _mapping(inventory_doc.get("total_expected"), "inventory.total_expected")
    gold_gate = tiers["gate"]
    gold_hourly = tiers["gate"] + tiers["hourly_extension"]
    gold_full = tiers["gate"] + tiers["hourly_extension"] + tiers["daily_extension"]
    expected_totals = {
        "gold_gate": gold_gate,
        "gold_hourly": gold_hourly,
        "gold_full": gold_full,
        "traffic_gate": 236,
        "traffic_hourly": 256,
        "traffic_full": 296,
    }
    for key, actual in expected_totals.items():
        if total_expected.get(key) != actual:
            raise InventoryError(f"total_expected.{key}: expected {actual}, actual {total_expected.get(key)!r}")

    all_tests = [
        node for node in _mapping(manifest_doc.get("nodes"), "manifest.nodes").values()
        if isinstance(node, Mapping) and node.get("resource_type") == "test"
    ]
    group_counts = Counter()
    static_tag_counts = Counter()
    for node in all_tests:
        tags = {str(tag) for tag in node.get("tags", [])}
        for static_tag in STATIC_TIER_TAGS:
            if static_tag in tags:
                static_tag_counts[static_tag] += 1
        for group, required_tags in PORTFOLIO_GROUP_TAGS.items():
            if tags & required_tags:
                group_counts[group] += 1
    if dict(group_counts) != EXPECTED_PORTFOLIO_COUNTS:
        raise InventoryError(
            f"manifest portfolio counts mismatch: expected {EXPECTED_PORTFOLIO_COUNTS}, actual {dict(group_counts)}"
        )
    if dict(static_tag_counts) != EXPECTED_STATIC_TAG_COUNTS:
        raise InventoryError(
            f"manifest static axes/admin counts mismatch: expected {EXPECTED_STATIC_TAG_COUNTS}, actual {dict(static_tag_counts)}"
        )

    cadence_counts = {
        "traffic_gate": group_counts["availability"] + group_counts["bronze_source"] + group_counts["silver"] + group_counts["gold_gate"],
        "traffic_hourly": group_counts["availability"] + group_counts["bronze_source"] + group_counts["silver"] + group_counts["gold_gate"] + group_counts["gold_hourly_extension"],
        "traffic_full": sum(group_counts.values()),
    }
    if cadence_counts != {"traffic_gate": 236, "traffic_hourly": 256, "traffic_full": 296}:
        raise InventoryError(f"manifest cadence counts mismatch: {cadence_counts}")

    if selector_counts is not None and dict(selector_counts) != EXPECTED_SELECTOR_COUNTS:
        raise InventoryError(
            f"selector counts mismatch: expected {EXPECTED_SELECTOR_COUNTS}, actual {dict(selector_counts)}"
        )


def parse_selector_counts(values: Sequence[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        name, separator, raw_count = value.partition("=")
        if not separator or name in counts:
            raise InventoryError(f"invalid selector count {value!r}")
        counts[name] = int(raw_count)
    return counts


def generate_candidate(manifest: object) -> dict[str, object]:
    manifest_doc = _mapping(manifest, "manifest")
    records = _manifest_test_records(manifest_doc)
    tests = []
    for unique_id in sorted(records):
        record = records[unique_id]
        owners = record["owner_unique_ids"]
        if not owners:
            raise InventoryError(f"{unique_id}: expected at least one model/seed owner unique id")
        tier = str(record["tier"])
        tier_tag = (
            GOLD_TIER_TAGS[tier]
            if tier in GOLD_TIER_TAGS
            else sorted(record["tags"] & STATIC_TIER_TAGS)[0]
        )
        tests.append(
            {
                "unique_id": unique_id,
                "path": record["path"],
                "test_type": record["test_type"],
                "owner_unique_ids": owners,
                "tier": tier,
                "tier_tag": tier_tag,
            }
        )
    return {
        "version": 1,
        "tiers": {
            "gate": {"expected_count": 123},
            "hourly_extension": {"expected_count": 20},
            "daily_extension": {"expected_count": 30},
            "full_static": {"expected_count": 10},
        },
        "total_expected": {
            "gold_gate": 123,
            "gold_hourly": 143,
            "gold_full": 173,
            "traffic_gate": 236,
            "traffic_hourly": 256,
            "traffic_full": 296,
        },
        "portfolio_expected": EXPECTED_PORTFOLIO_COUNTS,
        "selector_expected": EXPECTED_SELECTOR_COUNTS,
        "cadence_expected": {"traffic_gate": 236, "traffic_hourly": 256, "traffic_full": 296},
        "tests": tests,
    }


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inventory", type=Path)
    mode.add_argument("--generate-candidate", type=Path)
    parser.add_argument(
        "--selector-count",
        action="append",
        default=[],
        metavar="NAME=COUNT",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _argument_parser().parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        if args.generate_candidate is not None:
            candidate = generate_candidate(manifest)
            args.generate_candidate.write_text(
                yaml.safe_dump(candidate, sort_keys=False), encoding="utf-8"
            )
            print("PASS: generated 183 candidate records (123/20/30/10)")
            return 0
        inventory = yaml.safe_load(args.inventory.read_text(encoding="utf-8"))
        selector_counts = parse_selector_counts(args.selector_count)
        validate_inventory(manifest, inventory, selector_counts=selector_counts)
    except (InventoryError, OSError, UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError) as error:
        print(f"ERROR: {error}")
        return 1
    print("PASS: traffic Gold test cadence inventory is valid (236/256/296)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run validator unit tests**

Run:

```powershell
cd domains/traffic_weather
python -m pytest contracts/traffic/tests/test_validate_traffic_gold_test_inventory.py -q
```

Expected:

```text
all validator tests passed
```

- [ ] **Step 5: Commit the validator skeleton only after user approval**

Run only after explicit approval:

```powershell
git add domains/traffic_weather/contracts/traffic/scripts/validate_traffic_gold_test_inventory.py domains/traffic_weather/contracts/traffic/tests/test_validate_traffic_gold_test_inventory.py
git commit -m "feat(traffic): add Gold cadence inventory validator"
```

Expected:

```text
[feat/257-traffic-gold-incremental-exact-set ...] feat(traffic): add Gold cadence inventory validator
```

### Task 5: Add tier tags and selectors without breaking the legacy full selector

**Files:**
- Modify: `domains/traffic_weather/models/traffic/transform/gold/_serving_gold.yml`
- Modify: `domains/traffic_weather/models/traffic/transform/gold/_gold.yml`
- Modify: `domains/traffic_weather/selectors.yml`
- Test: `domains/traffic_weather/workflows/tests/test_premerge_gate.py`

**Interfaces:**
- Consumes: dbt test tags and existing `ask_seoul_traffic_transform_gold`.
- Produces:
  - `ask_seoul_traffic_transform_gold_models`
  - `ask_seoul_traffic_transform_gold_gate_tests`
  - `ask_seoul_traffic_transform_gold_hourly_tests`
  - `ask_seoul_traffic_transform_gold_full_tests`

- [ ] **Step 1: Add selector unit assertions**

Append to `domains/traffic_weather/workflows/tests/test_premerge_gate.py`:

```python
def test_traffic_gold_cadence_selectors_are_declared() -> None:
    selectors_path = PROJECT_ROOT / "selectors.yml"
    document = yaml.safe_load(selectors_path.read_text(encoding="utf-8")) or {}
    selector_names = {selector["name"] for selector in document["selectors"]}

    assert "ask_seoul_traffic_transform_gold" in selector_names
    assert "ask_seoul_traffic_transform_gold_models" in selector_names
    assert "ask_seoul_traffic_transform_gold_gate_tests" in selector_names
    assert "ask_seoul_traffic_transform_gold_hourly_tests" in selector_names
    assert "ask_seoul_traffic_transform_gold_full_tests" in selector_names

    def walk(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)

    cadence_definitions = (
        selector["definition"]
        for selector in document["selectors"]
        if selector["name"] in {
            "ask_seoul_traffic_transform_gold_gate_tests",
            "ask_seoul_traffic_transform_gold_hourly_tests",
            "ask_seoul_traffic_transform_gold_full_tests",
        }
    )
    assert all(
        node.get("method") != "selector"
        for definition in cadence_definitions
        for node in walk(definition)
    )
```

- [ ] **Step 2: Run selector declaration test and verify it fails**

Run:

```powershell
cd domains/traffic_weather
python -m pytest workflows/tests/test_premerge_gate.py::test_traffic_gold_cadence_selectors_are_declared -q
```

Expected:

```text
FAILED ... ask_seoul_traffic_transform_gold_models
```

- [ ] **Step 3: Add selectors**

Append these selector definitions after the existing `ask_seoul_traffic_transform_gold` entry in `domains/traffic_weather/selectors.yml`:

```yaml
  - name: ask_seoul_traffic_transform_gold_models
    description: Traffic scheduled Gold model nodes only; tests are excluded for cadence-specific gates.
    definition:
      intersection:
        - method: tag
          value: ask_seoul_traffic_transform_gold
          indirect_selection: empty
        - method: resource_type
          value: model

  - name: ask_seoul_traffic_transform_gold_gate_tests
    description: Traffic Gold fast gate tests selected every transform run.
    definition:
      intersection:
        - method: tag
          value: ask_seoul_traffic_transform_gold
          indirect_selection: empty
        - method: tag
          value: traffic_gold_gate
          indirect_selection: empty
        - method: resource_type
          value: test

  - name: ask_seoul_traffic_transform_gold_hourly_tests
    description: Traffic Gold hourly assurance tests; includes gate tests plus hourly extensions.
    definition:
      union:
        - intersection:
            - method: tag
              value: ask_seoul_traffic_transform_gold
              indirect_selection: empty
            - method: tag
              value: traffic_gold_gate
              indirect_selection: empty
            - method: resource_type
              value: test
        - intersection:
            - method: tag
              value: ask_seoul_traffic_transform_gold
              indirect_selection: empty
            - method: tag
              value: traffic_gold_hourly_extension
              indirect_selection: empty
            - method: resource_type
              value: test

  - name: ask_seoul_traffic_transform_gold_full_tests
    description: Traffic Gold full assurance tests; includes gate, hourly extension, and daily extension tests.
    definition:
      union:
        - intersection:
            - method: tag
              value: ask_seoul_traffic_transform_gold
              indirect_selection: empty
            - method: tag
              value: traffic_gold_gate
              indirect_selection: empty
            - method: resource_type
              value: test
        - intersection:
            - method: tag
              value: ask_seoul_traffic_transform_gold
              indirect_selection: empty
            - method: tag
              value: traffic_gold_hourly_extension
              indirect_selection: empty
            - method: resource_type
              value: test
        - intersection:
            - method: tag
              value: ask_seoul_traffic_transform_gold
              indirect_selection: empty
            - method: tag
              value: traffic_gold_daily_extension
              indirect_selection: empty
            - method: resource_type
              value: test
```

Do not change existing `ask_seoul_traffic_transform_gold`.

- [ ] **Step 4: Add tier tags to generic tests in YAML**

For generic tests in `_serving_gold.yml` and `_gold.yml`, use this pattern:

```yaml
        tests:
          - not_null:
              config:
                tags: ["traffic_gold_gate"]
          - unique:
              config:
                tags: ["traffic_gold_gate"]
```

For accepted-values tests that belong to hourly extension:

```yaml
          - accepted_values:
              arguments:
                values: ['matched', 'missing_flow']
              config:
                tags: ["traffic_gold_hourly_extension"]
```

For daily/full reconciliation tests:

```yaml
          - accepted_values:
              arguments:
                values:
                  - manifest_missing
                  - api_failure
                  - manifest_not_publishable
                  - materialized_partial
                  - materialized_zero
                  - materialized_consistent
              config:
                tags: ["traffic_gold_daily_extension"]
```

- [ ] **Step 5: Add tier tags to singular SQL tests**

At the top of each singular test selected for gate, add:

```sql
{{ config(tags=['traffic_gold_gate']) }}
```

At the top of each singular test selected for hourly extension, add:

```sql
{{ config(tags=['traffic_gold_hourly_extension']) }}
```

At the top of each singular test selected for daily extension, add:

```sql
{{ config(tags=['traffic_gold_daily_extension']) }}
```

Keep existing `-- depends_on:` lines below the config line, for example:

```sql
{{ config(tags=['traffic_gold_gate']) }}
-- depends_on: {{ ref('gold_traffic_incident_x_flow') }}
```

- [ ] **Step 6: Verify selectors are non-empty and countable**

Run:

```powershell
cd domains/traffic_weather
dbt parse --no-partial-parse --target dev --target-path target/gold-selector-parse --vars '{"traffic_snapshot_dag_run_id":"ci__traffic-gold-selector","traffic_flow_snapshot_dag_run_id":"ci__traffic-gold-selector","traffic_citydata_crowding_snapshot_id":1}'
dbt ls --selector ask_seoul_traffic_transform_gold_models --target dev --target-path target/gold-selector-parse --output name --quiet
dbt ls --selector ask_seoul_traffic_transform_gold_gate_tests --target dev --target-path target/gold-selector-parse --output name --quiet
dbt ls --selector ask_seoul_traffic_transform_gold_hourly_tests --target dev --target-path target/gold-selector-parse --output name --quiet
dbt ls --selector ask_seoul_traffic_transform_gold_full_tests --target dev --target-path target/gold-selector-parse --output name --quiet
```

Expected:

```text
gold model selector is non-empty
gate test selector emits 123 tests
hourly test selector emits 143 tests
full test selector emits 173 tests
```

- [ ] **Step 7: Run selector declaration test**

Run:

```powershell
cd domains/traffic_weather
python -m pytest workflows/tests/test_premerge_gate.py::test_traffic_gold_cadence_selectors_are_declared -q
```

Expected:

```text
1 passed
```

- [ ] **Step 8: Commit this task only after user approval**

Run only after explicit approval:

```powershell
git add domains/traffic_weather/models/traffic/transform/gold/_serving_gold.yml domains/traffic_weather/models/traffic/transform/gold/_gold.yml domains/traffic_weather/selectors.yml domains/traffic_weather/tests/traffic/transform/gold domains/traffic_weather/workflows/tests/test_premerge_gate.py
git commit -m "feat(traffic): split Gold test cadence selectors"
```

Expected:

```text
[feat/257-traffic-gold-incremental-exact-set ...] feat(traffic): split Gold test cadence selectors
```

### Task 6: Generate, review, and track the exact inventory

**Files:**
- Create: `domains/traffic_weather/contracts/traffic_gold_test_cadence.yml`

**Interfaces:**
- Consumes: Task 4 generator/validator and Task 5 manifest tags/selectors.
- Produces: reviewed canonical inventory with 183 exact records: `gate=123`, `hourly_extension=20`, `daily_extension=30`, `full_static=10`.

- [ ] **Step 1: Add a candidate-generation test to the Task 4 test module**

```python
def test_candidate_contains_manifest_identity_and_contract_fields(validator) -> None:
    candidate = validator.generate_candidate(_manifest())
    record = candidate["tests"][0]
    assert set(record) == {
        "unique_id", "path", "test_type", "owner_unique_ids", "tier", "tier_tag"
    }
    assert candidate["portfolio_expected"] == {
        "availability": 1,
        "bronze_source": 70,
        "silver": 42,
        "gold_gate": 123,
        "gold_hourly_extension": 20,
        "gold_daily_extension": 30,
        "full_static": 10,
    }
```

- [ ] **Step 2: Generate one fresh manifest and selector artifacts after tags/selectors exist**

```powershell
cd domains/traffic_weather
$targetPath = 'target/traffic-gold-inventory-review'
$parseVars = @{traffic_snapshot_dag_run_id='ci__traffic-gold-inventory';traffic_flow_snapshot_dag_run_id='ci__traffic-gold-inventory';traffic_citydata_crowding_snapshot_id=1} | ConvertTo-Json -Compress
dbt parse --no-partial-parse --target dev --target-path $targetPath --vars $parseVars
dbt ls --resource-type test --selector ask_seoul_traffic_transform_gold_gate_tests --target dev --target-path $targetPath --vars $parseVars --output unique_id --quiet | Set-Content -Encoding utf8 "$targetPath/gold-gate.txt"
dbt ls --resource-type test --selector ask_seoul_traffic_transform_gold_hourly_tests --target dev --target-path $targetPath --vars $parseVars --output unique_id --quiet | Set-Content -Encoding utf8 "$targetPath/gold-hourly.txt"
dbt ls --resource-type test --selector ask_seoul_traffic_transform_gold_full_tests --target dev --target-path $targetPath --vars $parseVars --output unique_id --quiet | Set-Content -Encoding utf8 "$targetPath/gold-full.txt"
```

Expected: files contain exactly `123`, `143`, and `173` non-empty lines.

- [ ] **Step 3: Generate the candidate YAML from manifest metadata, including axes and admin static tags**

Task 4's CLI must expose `--generate-candidate`; it classifies `full_static` when a test has either `ask_seoul_traffic_transform_asac_axes_contract` or `ask_seoul_traffic_transform_common_admin`.

```powershell
python contracts/traffic/scripts/validate_traffic_gold_test_inventory.py --manifest target/traffic-gold-inventory-review/manifest.json --generate-candidate target/traffic-gold-inventory-review/traffic_gold_test_cadence.candidate.yml
```

Expected:

```text
PASS: generated 183 candidate records (123/20/30/10)
```

- [ ] **Step 4: Review every candidate record before promotion**

For each record, compare `unique_id`, normalized `path`, manifest-derived `test_type`, the exact sorted `owner_unique_ids` from model/seed entries in `depends_on.nodes`, and `tier_tag`. Reject the candidate if any Gold test lacks exactly one of `traffic_gold_gate`, `traffic_gold_hourly_extension`, `traffic_gold_daily_extension`, or if a static test lacks both static tags. Confirm manifest group counts `1/70/42/123/20/30/10`, selector counts `123/143/173`, and cadence totals `236/256/296`.

```powershell
$candidate = Get-Content -Raw target/traffic-gold-inventory-review/traffic_gold_test_cadence.candidate.yml
$candidate | Set-Content -Encoding utf8 contracts/traffic_gold_test_cadence.yml
git diff -- contracts/traffic_gold_test_cadence.yml
```

Expected: the diff contains all 183 reviewed records and no generated path outside the canonical inventory file.

- [ ] **Step 5: Validate the promoted inventory against the same manifest and selector counts**

```powershell
python contracts/traffic/scripts/validate_traffic_gold_test_inventory.py --manifest target/traffic-gold-inventory-review/manifest.json --inventory contracts/traffic_gold_test_cadence.yml --selector-count ask_seoul_traffic_transform_gold_gate_tests=123 --selector-count ask_seoul_traffic_transform_gold_hourly_tests=143 --selector-count ask_seoul_traffic_transform_gold_full_tests=173
```

Expected: `PASS: traffic Gold test cadence inventory is valid (236/256/296)`.

- [ ] **Step 6: Commit only after user approval**

```powershell
git add domains/traffic_weather/contracts/traffic_gold_test_cadence.yml
git commit -m "test(traffic): pin reviewed Gold cadence inventory"
```

### Task 7: Wire exact inventory validation into premerge

**Files:**
- Modify: `domains/traffic_weather/workflows/premerge_gate.py`
- Modify: `domains/traffic_weather/workflows/tests/test_premerge_gate.py`

**Interfaces:**
- Consumes: Task 4 validator script and Task 5 selectors.
- Produces: premerge sequence that captures every named selector count, fails exact Gold selector drift at `123/143/173`, passes those counts to the inventory validator, then runs pytest and the singular dependency validator.

- [ ] **Step 1: Make selector validation return counts and fail exact Gold selector drift**

Keep the existing `dbt ls` command construction and replace its result handling/return contract as follows:

Ensure the module imports `Mapping`:

```python
from typing import Mapping
```

```python
EXACT_SELECTOR_COUNTS = {
    "ask_seoul_traffic_transform_gold_gate_tests": 123,
    "ask_seoul_traffic_transform_gold_hourly_tests": 143,
    "ask_seoul_traffic_transform_gold_full_tests": 173,
}


def validate_named_selectors(
    *,
    project_dir: Path,
    target_path: Path,
    dbt_bin: str,
    snapshot_run_id: str,
    environment: dict[str, str],
    command_runner: CommandRunner,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for selector in _selector_names(project_dir):
        result = command_runner(
            [
                dbt_bin,
                "ls",
                "--selector",
                selector,
                "--target",
                "dev",
                "--target-path",
                str(target_path),
                "--vars",
                _manifest_vars(snapshot_run_id),
                "--output",
                "unique_id",
                "--quiet",
            ],
            check=True,
            cwd=project_dir,
            env=environment,
            capture_output=True,
            text=True,
        )
        selected = [line for line in result.stdout.splitlines() if line.strip()]
        if not selected:
            raise RuntimeError(f"named selector {selector!r} is empty")
        counts[selector] = len(selected)
    actual_exact = {name: counts.get(name, 0) for name in EXACT_SELECTOR_COUNTS}
    if actual_exact != EXACT_SELECTOR_COUNTS:
        raise RuntimeError(
            f"Traffic Gold selector counts mismatch: expected {EXACT_SELECTOR_COUNTS}, actual {actual_exact}"
        )
    return counts
```

Add unit cases proving `122/143/173`, `123/142/173`, and `123/143/172` fail before pytest, while `123/143/173` continues.

- [ ] **Step 2: Update premerge test expected command sequence**

In `test_gate_owns_the_complete_read_only_premerge_sequence`, update expected commands so the inventory validator runs after selector validation and before pytest:

```python
assert commands[5] == [
    sys.executable,
    str(
        project_dir
        / "contracts"
        / "traffic"
        / "scripts"
        / "validate_traffic_gold_test_inventory.py"
    ),
    "--manifest",
    str(target_path / "manifest.json"),
    "--inventory",
    str(project_dir / "contracts" / "traffic_gold_test_cadence.yml"),
    "--selector-count",
    "ask_seoul_traffic_transform_gold_gate_tests=123",
    "--selector-count",
    "ask_seoul_traffic_transform_gold_hourly_tests=143",
    "--selector-count",
    "ask_seoul_traffic_transform_gold_full_tests=173",
]
assert commands[6] == [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
assert commands[7] == [
    sys.executable,
    str(
        project_dir
        / "contracts"
        / "traffic"
        / "scripts"
        / "validate_singular_test_dependency_manifest.py"
    ),
    "--manifest",
    str(target_path / "manifest.json"),
]
```

Also assert both vars are passed to parse and ls:

```python
vars_payload = parse_command[parse_command.index("--vars") + 1]
assert "ci__snapshot" in vars_payload
assert "traffic_snapshot_dag_run_id" in vars_payload
assert "traffic_flow_snapshot_dag_run_id" in vars_payload
```

- [ ] **Step 3: Run premerge test and verify it fails**

Run:

```powershell
cd domains/traffic_weather
python -m pytest workflows/tests/test_premerge_gate.py::test_gate_owns_the_complete_read_only_premerge_sequence -q
```

Expected:

```text
FAILED ... validate_traffic_gold_test_inventory.py
```

- [ ] **Step 4: Update `_manifest_vars`**

In `domains/traffic_weather/workflows/premerge_gate.py`, replace `_manifest_vars` with:

```python
def _manifest_vars(snapshot_run_id: str) -> str:
    return json.dumps(
        {
            "traffic_snapshot_dag_run_id": snapshot_run_id,
            "traffic_flow_snapshot_dag_run_id": snapshot_run_id,
            "traffic_citydata_crowding_snapshot_id": 1,
        }
    )
```

This keeps premerge parse read-only and deterministic. The `traffic_citydata_crowding_snapshot_id` value is a parse-time positive sentinel for macros that fail closed when absent at execute time.

- [ ] **Step 5: Add inventory validation function and call it**

Add this function after `validate_named_selectors`:

```python
def validate_traffic_gold_test_inventory(
    *,
    project_dir: Path,
    manifest_path: Path,
    selector_counts: Mapping[str, int],
    command_runner: CommandRunner,
) -> None:
    """Fail when Traffic Gold test tier inventory differs from the fresh manifest."""
    selector_count_args = [
        item
        for name in EXACT_SELECTOR_COUNTS
        for item in ("--selector-count", f"{name}={selector_counts[name]}")
    ]
    command_runner(
        [
            sys.executable,
            str(
                project_dir
                / "contracts"
                / "traffic"
                / "scripts"
                / "validate_traffic_gold_test_inventory.py"
            ),
            "--manifest",
            str(manifest_path),
            "--inventory",
            str(project_dir / "contracts" / "traffic_gold_test_cadence.yml"),
            *selector_count_args,
        ],
        check=True,
        cwd=project_dir,
    )
```

Then call it in `run_premerge_gate` immediately after `validate_named_selectors(...)`:

```python
    selector_counts = validate_named_selectors(
        project_dir=project_dir,
        target_path=target_path,
        dbt_bin=dbt_bin,
        snapshot_run_id=snapshot_run_id,
        environment=environment,
        command_runner=command_runner,
    )
    validate_traffic_gold_test_inventory(
        project_dir=project_dir,
        manifest_path=manifest_path,
        selector_counts=selector_counts,
        command_runner=command_runner,
    )
```

- [ ] **Step 6: Run premerge unit tests**

Run:

```powershell
cd domains/traffic_weather
python -m pytest workflows/tests/test_premerge_gate.py -q
```

Expected:

```text
all tests passed
```

- [ ] **Step 7: Commit this task only after user approval**

Run only after explicit approval:

```powershell
git add domains/traffic_weather/workflows/premerge_gate.py domains/traffic_weather/workflows/tests/test_premerge_gate.py
git commit -m "feat(traffic): validate Gold test cadence in premerge"
```

Expected:

```text
[feat/257-traffic-gold-incremental-exact-set ...] feat(traffic): validate Gold test cadence in premerge
```

### Task 8: Add shadow parity 3-cycle analysis and canary commands

**Files:**
- Create: `domains/traffic_weather/analyses/traffic/traffic_gold_flow_shadow_parity.sql`
- Optionally document results in existing `LessonRun.md` only during smoke execution, not in this task unless requested.

**Interfaces:**
- Consumes: old table relations, shadow incremental relations, model name vars.
- Produces: one SQL analysis returning parity failure rows; zero rows means pass.

- [ ] **Step 1: Create shadow parity analysis SQL**

Create `domains/traffic_weather/analyses/traffic/traffic_gold_flow_shadow_parity.sql`:

```sql
{% set old_schema = var('traffic_gold_old_schema', 'traffic_gold_reference') %}
{% set shadow_schema = var('traffic_gold_shadow_schema', 'traffic_gold_candidate') %}
{% set model_name = var('traffic_gold_parity_model', 'gold_traffic_flow_link_latest') %}
{% set grain_columns = var('traffic_gold_parity_grain_columns', ['link_id']) %}

with old_relation as (
    select * from {{ target.database }}.{{ old_schema }}.{{ model_name }}
),

shadow_relation as (
    select * from {{ target.database }}.{{ shadow_schema }}.{{ model_name }}
),

old_minus_shadow as (
    select 'old_minus_shadow' as failure_reason, count(*) as failure_count
    from (
        select * from old_relation
        except
        select * from shadow_relation
    )
),

shadow_minus_old as (
    select 'shadow_minus_old' as failure_reason, count(*) as failure_count
    from (
        select * from shadow_relation
        except
        select * from old_relation
    )
),

shadow_duplicate_grain as (
    select 'shadow_duplicate_grain' as failure_reason, count(*) as failure_count
    from (
        select
            {% for column_name in grain_columns %}
            {{ column_name }}{% if not loop.last %},{% endif %}
            {% endfor %}
        from shadow_relation
        group by
            {% for column_name in grain_columns %}
            {{ column_name }}{% if not loop.last %},{% endif %}
            {% endfor %}
        having count(*) > 1
    )
),

row_count_delta as (
    select
        'row_count_delta' as failure_reason,
        abs((select count(*) from old_relation) - (select count(*) from shadow_relation)) as failure_count
)

select *
from old_minus_shadow
where failure_count <> 0
union all
select *
from shadow_minus_old
where failure_count <> 0
union all
select *
from shadow_duplicate_grain
where failure_count <> 0
union all
select *
from row_count_delta
where failure_count <> 0
```

- [ ] **Step 2: Compile the analysis**

Run:

```powershell
cd domains/traffic_weather
dbt compile --select traffic_gold_flow_shadow_parity --target dev --target-path target/shadow-parity-compile --vars '{"traffic_snapshot_dag_run_id":"ci__traffic-gold-shadow","traffic_flow_snapshot_dag_run_id":"ci__traffic-gold-shadow","traffic_citydata_crowding_snapshot_id":1}'
```

Expected:

```text
Completed successfully
```

- [ ] **Step 3: Run shadow parity cycle 1, initial full build**

In dev only, do not overwrite serving Gold/Silver. Create fixed reference/candidate schemas and copy serving Silver into each schema with Trino CTAS before each build cycle:

```powershell
cd domains/traffic_weather
$requiredEnv = @(
  "TRAFFIC_INCIDENT_RUN_ID",
  "TRAFFIC_FLOW_RUN_ID",
  "TRAFFIC_LATE_FLOW_RUN_ID",
  "TRAFFIC_CITYDATA_SNAPSHOT_ID"
)
$missingEnv = $requiredEnv | Where-Object { [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($_)) }
if ($missingEnv) { throw "Missing required env vars: $($missingEnv -join ', ')" }

$referenceSchema = "traffic_gold_reference"
$candidateSchema = "traffic_gold_candidate"
$catalog = if ([string]::IsNullOrWhiteSpace($env:TRINO_DEV_ICEBERG_CATALOG)) { "iceberg_dev" } else { $env:TRINO_DEV_ICEBERG_CATALOG }
$servingTrafficSchema = if ([string]::IsNullOrWhiteSpace($env:TRAFFIC_SCHEMA)) { "traffic" } else { $env:TRAFFIC_SCHEMA }
$models = "gold_traffic_flow_link_latest gold_traffic_flow_change_latest gold_traffic_flow_congestion_hotspots_hourly gold_traffic_flow_link_time_profile"
$varsCycle1 = @{
  traffic_snapshot_dag_run_id = $env:TRAFFIC_INCIDENT_RUN_ID
  traffic_flow_snapshot_dag_run_id = $env:TRAFFIC_FLOW_RUN_ID
  traffic_citydata_crowding_snapshot_id = [int]$env:TRAFFIC_CITYDATA_SNAPSHOT_ID
} | ConvertTo-Json -Compress

trino --execute "create schema if not exists $catalog.$referenceSchema"
trino --execute "create schema if not exists $catalog.$candidateSchema"
trino --execute "create or replace table $catalog.$referenceSchema.silver_seoul_traffic_flow as select * from $catalog.$servingTrafficSchema.silver_seoul_traffic_flow"
trino --execute "create or replace table $catalog.$candidateSchema.silver_seoul_traffic_flow as select * from $catalog.$servingTrafficSchema.silver_seoul_traffic_flow"
$previousTrafficSchema = $env:TRAFFIC_SCHEMA
try {
  $env:TRAFFIC_SCHEMA = $referenceSchema
  dbt build --select $models --full-refresh --target dev --vars $varsCycle1
  $env:TRAFFIC_SCHEMA = $candidateSchema
  dbt build --select $models --full-refresh --target dev --vars $varsCycle1
} finally {
  $env:TRAFFIC_SCHEMA = $previousTrafficSchema
}
```

Expected:

```text
Completed successfully
```

Then run parity for each model:

```powershell
dbt show --select traffic_gold_flow_shadow_parity --target dev --vars (@{
  traffic_gold_old_schema = $referenceSchema
  traffic_gold_shadow_schema = $candidateSchema
  traffic_gold_parity_model = "gold_traffic_flow_link_latest"
  traffic_gold_parity_grain_columns = @("link_id")
  traffic_snapshot_dag_run_id = $env:TRAFFIC_INCIDENT_RUN_ID
  traffic_flow_snapshot_dag_run_id = $env:TRAFFIC_FLOW_RUN_ID
  traffic_citydata_crowding_snapshot_id = [int]$env:TRAFFIC_CITYDATA_SNAPSHOT_ID
} | ConvertTo-Json -Compress)
```

Expected:

```text
0 rows returned
```

Repeat with grain columns:

```json
["link_id"]
["link_id"]
["hour_at", "link_id"]
["link_id", "kst_day_of_week", "kst_hour"]
```

- [ ] **Step 4: Run shadow parity cycle 2, identical replay**

Run the same Flow run id again against the candidate incremental relations. Reference relations are rebuilt with full-refresh from the fixed reference Silver copy; candidate relations run incremental against the fixed candidate Silver copy:

```powershell
cd domains/traffic_weather
$previousTrafficSchema = $env:TRAFFIC_SCHEMA
try {
  $env:TRAFFIC_SCHEMA = $referenceSchema
  dbt build --select $models --full-refresh --target dev --vars $varsCycle1
  $env:TRAFFIC_SCHEMA = $candidateSchema
  dbt build --select $models --target dev --vars $varsCycle1
} finally {
  $env:TRAFFIC_SCHEMA = $previousTrafficSchema
}
```

Expected:

```text
Completed successfully
```

Run all four parity checks again.

Expected:

```text
0 rows returned for old_minus_shadow
0 rows returned for shadow_minus_old
0 rows returned for shadow_duplicate_grain
0 row_count_delta
```

- [ ] **Step 5: Run shadow parity cycle 3, new snapshot or late-arrival fixture**

Use a different publishable Flow run id that touches a subset of links/hours/profile cells. First refresh both serving Silver copies with Trino CTAS after the upstream serving Silver copy contains the new Flow pin; then rebuild reference full-refresh and candidate incremental:

```powershell
cd domains/traffic_weather
$varsCycle3 = @{
  traffic_snapshot_dag_run_id = $env:TRAFFIC_INCIDENT_RUN_ID
  traffic_flow_snapshot_dag_run_id = $env:TRAFFIC_LATE_FLOW_RUN_ID
  traffic_citydata_crowding_snapshot_id = [int]$env:TRAFFIC_CITYDATA_SNAPSHOT_ID
} | ConvertTo-Json -Compress
trino --execute "create or replace table $catalog.$referenceSchema.silver_seoul_traffic_flow as select * from $catalog.$servingTrafficSchema.silver_seoul_traffic_flow"
trino --execute "create or replace table $catalog.$candidateSchema.silver_seoul_traffic_flow as select * from $catalog.$servingTrafficSchema.silver_seoul_traffic_flow"
$previousTrafficSchema = $env:TRAFFIC_SCHEMA
try {
  $env:TRAFFIC_SCHEMA = $referenceSchema
  dbt build --select $models --full-refresh --target dev --vars $varsCycle3
  $env:TRAFFIC_SCHEMA = $candidateSchema
  dbt build --select $models --target dev --vars $varsCycle3
} finally {
  $env:TRAFFIC_SCHEMA = $previousTrafficSchema
}
```

Expected:

```text
Completed successfully
```

Run all four parity checks again.

Expected:

```text
0 rows returned for every parity query
```

- [ ] **Step 6: Run optional Flow no-op canary**

Omit `traffic_flow_snapshot_dag_run_id`:

```powershell
cd domains/traffic_weather
$varsNoFlow = @{
  traffic_snapshot_dag_run_id = $env:TRAFFIC_INCIDENT_RUN_ID
  traffic_citydata_crowding_snapshot_id = [int]$env:TRAFFIC_CITYDATA_SNAPSHOT_ID
} | ConvertTo-Json -Compress
$previousTrafficSchema = $env:TRAFFIC_SCHEMA
try {
  $env:TRAFFIC_SCHEMA = $candidateSchema
  dbt build --select $models --target dev --vars $varsNoFlow
} finally {
  $env:TRAFFIC_SCHEMA = $previousTrafficSchema
}
```

Expected:

```text
Completed successfully
```

Record before/after row counts for all four Flow Gold targets. Expected: all row counts unchanged.

- [ ] **Step 7: Run non-empty pin zero-row fail-closed canary**

Use a syntactically valid but absent Flow run id:

```powershell
cd domains/traffic_weather
$varsAbsentFlow = @{
  traffic_snapshot_dag_run_id = $env:TRAFFIC_INCIDENT_RUN_ID
  traffic_flow_snapshot_dag_run_id = "ci__absent_flow_run_for_fail_closed"
  traffic_citydata_crowding_snapshot_id = [int]$env:TRAFFIC_CITYDATA_SNAPSHOT_ID
} | ConvertTo-Json -Compress
$previousTrafficSchema = $env:TRAFFIC_SCHEMA
try {
  $env:TRAFFIC_SCHEMA = $candidateSchema
  dbt build --select gold_traffic_flow_link_latest --target dev --vars $varsAbsentFlow
} finally {
  $env:TRAFFIC_SCHEMA = $previousTrafficSchema
}
```

Expected:

```text
Compilation Error
no silver_seoul_traffic_flow rows for pinned traffic_flow_snapshot_dag_run_id
```

- [ ] **Step 8: Commit this task only after user approval**

Run only after explicit approval:

```powershell
git add domains/traffic_weather/analyses/traffic/traffic_gold_flow_shadow_parity.sql
git commit -m "test(traffic): add Flow Gold shadow parity canary"
```

Expected:

```text
[feat/257-traffic-gold-incremental-exact-set ...] test(traffic): add Flow Gold shadow parity canary
```

### Task 9: Full validation sequence

**Files:**
- No new files.
- Validates all files changed by Tasks 1-8.

**Interfaces:**
- Consumes: complete branch implementation.
- Produces: evidence for PR body and `LessonRun.md` smoke report.

- [ ] **Step 1: Run Python unit/static tests**

Run:

```powershell
cd domains/traffic_weather
python -m pytest -q -p no:cacheprovider
```

Expected:

```text
all tests passed
```

- [ ] **Step 2: Generate fresh manifest**

Run:

```powershell
cd domains/traffic_weather
dbt deps
dbt parse --no-partial-parse --target dev --target-path target/traffic-gold-final-gate --vars '{"traffic_snapshot_dag_run_id":"ci__traffic-gold-final-gate","traffic_flow_snapshot_dag_run_id":"ci__traffic-gold-final-gate","traffic_citydata_crowding_snapshot_id":1}'
```

Expected:

```text
Done.
```

- [ ] **Step 3: Validate named selectors**

Run:

```powershell
cd domains/traffic_weather
dbt ls --selector ask_seoul_traffic_transform_gold_models --target dev --target-path target/traffic-gold-final-gate --output name --quiet
dbt ls --selector ask_seoul_traffic_transform_gold_gate_tests --target dev --target-path target/traffic-gold-final-gate --output name --quiet
dbt ls --selector ask_seoul_traffic_transform_gold_hourly_tests --target dev --target-path target/traffic-gold-final-gate --output name --quiet
dbt ls --selector ask_seoul_traffic_transform_gold_full_tests --target dev --target-path target/traffic-gold-final-gate --output name --quiet
```

Expected:

```text
gold_models: non-empty
gold_gate_tests: 123 tests
gold_hourly_tests: 143 tests
gold_full_tests: 173 tests
```

- [ ] **Step 4: Validate exact inventory**

Run:

```powershell
cd domains/traffic_weather
python contracts/traffic/scripts/validate_traffic_gold_test_inventory.py --manifest target/traffic-gold-final-gate/manifest.json --inventory contracts/traffic_gold_test_cadence.yml --selector-count ask_seoul_traffic_transform_gold_gate_tests=123 --selector-count ask_seoul_traffic_transform_gold_hourly_tests=143 --selector-count ask_seoul_traffic_transform_gold_full_tests=173
```

Expected:

```text
PASS: traffic Gold test cadence inventory is valid
```

- [ ] **Step 5: Validate singular dependency manifest**

Run:

```powershell
cd domains/traffic_weather
python contracts/traffic/scripts/validate_singular_test_dependency_manifest.py --manifest target/traffic-gold-final-gate/manifest.json
```

Expected:

```text
PASS: traffic singular-test dependency manifest is valid
```

- [ ] **Step 6: Run dbt build for Flow Gold with real dev pinned vars**

Run with actual dev run ids and do not print secrets:

```powershell
cd domains/traffic_weather
$requiredEnv = @("TRAFFIC_INCIDENT_RUN_ID", "TRAFFIC_FLOW_RUN_ID", "TRAFFIC_CITYDATA_SNAPSHOT_ID")
$missingEnv = $requiredEnv | Where-Object { [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($_)) }
if ($missingEnv) { throw "Missing required env vars: $($missingEnv -join ', ')" }
$vars = @{
  traffic_snapshot_dag_run_id = $env:TRAFFIC_INCIDENT_RUN_ID
  traffic_flow_snapshot_dag_run_id = $env:TRAFFIC_FLOW_RUN_ID
  traffic_citydata_crowding_snapshot_id = [int]$env:TRAFFIC_CITYDATA_SNAPSHOT_ID
} | ConvertTo-Json -Compress
dbt build --select silver_seoul_traffic_flow gold_traffic_flow_link_latest gold_traffic_flow_change_latest gold_traffic_flow_congestion_hotspots_hourly gold_traffic_flow_link_time_profile --target dev --vars $vars
```

Expected:

```text
Completed successfully
```

- [ ] **Step 7: Run cadence-level dbt tests**

Run:

```powershell
cd domains/traffic_weather
dbt test --selector ask_seoul_traffic_transform_gold_gate_tests --target dev --vars $vars
dbt test --selector ask_seoul_traffic_transform_gold_hourly_tests --target dev --vars $vars
dbt test --selector ask_seoul_traffic_transform_gold_full_tests --target dev --vars $vars
```

Expected:

```text
gate: 123 tests pass
hourly: 143 tests pass
full: 173 tests pass
```

- [ ] **Step 8: Run complete premerge workflow locally**

Run:

```powershell
cd C:\Users\Dell3571\Desktop\Projects\ask-seoul-worktrees\dbt-257-traffic-gold-incremental
python domains/traffic_weather/workflows/premerge_gate.py run --repository-root . --project-dir domains/traffic_weather --target-path domains/traffic_weather/target/premerge-local --base-sha origin/dev --head-sha HEAD --dbt-bin dbt --snapshot-run-id ci__traffic-gold-premerge-local
```

Expected:

```text
PASS: traffic Gold test cadence inventory is valid
PASS: traffic singular-test dependency manifest is valid
```

- [ ] **Step 9: Record smoke evidence**

In `LessonRun.md`, record only after running real dev smoke:

```markdown
## 2026-07-18 Traffic Gold incremental exact-set smoke

- DAG run id: `$env:TRAFFIC_DAG_RUN_ID`
- Incident pinned run id: `$env:TRAFFIC_INCIDENT_RUN_ID`
- Flow pinned run id: `$env:TRAFFIC_FLOW_RUN_ID`
- Late/new Flow pinned run id: `$env:TRAFFIC_LATE_FLOW_RUN_ID`
- Citydata snapshot id: `$env:TRAFFIC_CITYDATA_SNAPSHOT_ID`
- Flow Gold affected key counts:
  - `gold_traffic_flow_link_latest`: `changed_link_count from validation query`
  - `gold_traffic_flow_change_latest`: `changed_link_count from validation query`
  - `gold_traffic_flow_congestion_hotspots_hourly`: `changed_hour_count from validation query`
  - `gold_traffic_flow_link_time_profile`: `changed_profile_key_count from validation query`
- Cadence counts:
  - Gate: 236 total / 123 Gold tests
  - Hourly: 256 total / 143 Gold tests
  - Full: 296 total / 173 Gold tests
- Shadow parity:
  - initial full build: 0 diff
  - identical replay: 0 diff
  - new or late Flow run: 0 diff
- Optional Flow no-op: target row counts unchanged
- Non-empty absent Flow pin: fail-closed observed
- Tables affected: dev Traffic Flow Gold 4 incremental targets only
```

- [ ] **Step 10: Final commit only after user approval**

Run only after explicit approval:

```powershell
git status --short
git add domains/traffic_weather
git commit -m "feat(traffic): validate Flow Gold incremental exact-set"
```

Expected:

```text
[feat/257-traffic-gold-incremental-exact-set ...] feat(traffic): validate Flow Gold incremental exact-set
```

## Acceptance Criteria

- `gold_traffic_flow_link_latest`, `gold_traffic_flow_change_latest`, `gold_traffic_flow_congestion_hotspots_hourly`, `gold_traffic_flow_link_time_profile` use `materialized='incremental'`, `incremental_strategy='merge'`, `views_enabled=false`, `on_table_exists='drop'`, and their exact unique keys.
- Flow Gold incremental source scope is derived from `traffic_flow_snapshot_dag_run_id` and `silver_seoul_traffic_flow`; no Gold-specific watermark is introduced.
- Incremental invocation with missing/empty Flow var is a no-op for existing Flow Gold targets.
- Incremental invocation with non-empty Flow var and zero matching Silver rows fails with `no silver_seoul_traffic_flow rows for pinned traffic_flow_snapshot_dag_run_id`.
- Current/exact Incident Gold 16개 remain table replacement models.
- `gold_traffic_incident_collection_coverage_5m` remains table replacement.
- Existing `ask_seoul_traffic_transform_gold` remains available and backward-compatible.
- New selectors resolve:
  - `ask_seoul_traffic_transform_gold_models`: non-empty model set
  - `ask_seoul_traffic_transform_gold_gate_tests`: 123 tests
  - `ask_seoul_traffic_transform_gold_hourly_tests`: 143 tests
  - `ask_seoul_traffic_transform_gold_full_tests`: 173 tests
- Traffic cadence totals are preserved:
  - Gate: 236 total
  - Hourly: 256 total
  - Full: 296 total
- Inventory validator fails on missing, extra, duplicate, or tier count mismatch.
- Shadow parity returns zero rows for initial full build, identical replay, and new/late Flow run cycle.
- Dev verification does not require prod bucket/schema and does not print secrets.

## Risk And Mitigation

- Risk: `dbt-trino` incremental temp relation uses a view by default and regresses Iceberg merge stability.
  - Mitigation: every Flow Gold incremental model explicitly sets `views_enabled=false` and `on_table_exists='drop'`.
- Risk: plain merge leaves stale current Incident rows.
  - Mitigation: static guard test forbids incremental materialization on current/exact 16 and coverage 1.
- Risk: hourly hotspot ranking is wrong if only changed rows are ranked.
  - Mitigation: affected-hour model re-reads all Silver rows for each affected hour before ranking.
- Risk: time-profile averages double count on replay.
  - Mitigation: profile model recomputes aggregate from Silver history for affected profile keys; it never combines target aggregate with source aggregate.
- Risk: selector counts drift silently when new tests are added.
  - Mitigation: tracked inventory plus premerge manifest validator fails missing/extra/duplicate tests.
- Risk: optional Flow transform changes targets when no Flow run is present.
  - Mitigation: changed rows macro emits `where 1 = 0` during incremental when Flow var is empty.
- Risk: absent pinned Flow run silently succeeds with no data.
  - Mitigation: pre-hook raises compiler error when non-empty pinned var has zero matching Silver rows.

## Stop Rules

- Stop and do not implement if any proposed change requires converting Incident current/exact models to plain incremental merge.
- Stop and ask for direction if the fresh manifest cannot reproduce the 296 total test inventory from the approved run artifact.
- Stop before prod full-refresh/drop or prod schema access.
- Stop if existing user changes in the same files conflict with this plan's edits; explain the conflict before proceeding.

## Self-Review Checklist

- Spec coverage: Flow 4 incremental, optional Flow no-op, non-empty pin fail-closed, current 16 + coverage table guard, exact inventory, selector totals, shadow parity, rollback/validation are all mapped to tasks.
- Red-flag scan: No step depends on an unspecified handler; snippets include concrete SQL, Python, YAML, and commands.
- Type consistency: Macro names in Task 1 match Flow SQL calls in Task 2 and static tests. Selector names in Task 5 match premerge validation in Task 6. Inventory totals match 123/20/30/10 and 236/256/296.
