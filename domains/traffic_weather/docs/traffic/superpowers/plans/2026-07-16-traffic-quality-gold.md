# Traffic Quality Gold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish exactly five defensible Traffic Quality Gold products, add the three approved new models, and classify gold_traffic_incident_summary as support-only without changing existing model behavior.

**Architecture:** Keep the existing pinned current-hour and incident-driving x-flow products unchanged. Build collection coverage from materialized request-audit rows joined to source/run latest effective manifest state, and build the two daily products from the pinned current incident Silver using occurrence-day and canonical-or-unmapped buckets. Contract tests stage metadata and physical inventory separately so the exact-five inventory stays intentionally RED until all three model files and YAML entries exist.

**Tech Stack:** dbt-core 1.10.22, dbt-trino 1.10.2, Trino SQL, Iceberg dev catalog, PyYAML, pytest

## Global Constraints

- Approved ship set is exactly five Traffic products: gold_traffic_incident_current_by_admin_dong_hourly, gold_traffic_incident_x_flow, gold_traffic_incident_collection_coverage_5m, gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily, and gold_traffic_incident_spatial_mapping_quality_daily.
- gold_traffic_incident_summary is support-only and is not part of the five.
- All repository edits stay under domains/traffic_weather/models/traffic/**, domains/traffic_weather/tests/traffic/**, and domains/traffic_weather/docs/traffic/**.
- Do not change common, weather, packages.yml, dbt_project.yml, profiles, selectors, DAGs, or project-root files.
- Do not add commit, push, PR, or merge steps. Repository Gate B happens only after integrated verification.
- Existing current-hour, x-flow, and summary SQL behavior is preserved.
- Manifest consumers call latest_manifest_run_state(...) before evaluating status or is_publishable.
- Synthetic run IDs are allowed only for dbt parse and dbt compile.
- Every dbt run and dbt test command uses DBT_TRAFFIC_VARS built from actual dev latest-effective SUCCESS+publishable incident and flow run IDs.
- Runtime writes use an isolated dev TRAFFIC_SCHEMA; common axes relations are read-only.
- No full refresh, production catalog/schema write, backfill, or DAG execution is part of this plan.

## Dev Runtime Preconditions

The implementation session must receive three real environment values: an isolated dev TRAFFIC_SCHEMA, the actual latest-effective SUCCESS+publishable incident run in TRAFFIC_SNAPSHOT_DAG_RUN_ID, and the actual latest-effective SUCCESS+publishable flow run in TRAFFIC_FLOW_SNAPSHOT_DAG_RUN_ID. Validate and serialize them without printing their values:

~~~bash
test -n "$TRAFFIC_SCHEMA"
test -n "$TRAFFIC_SNAPSHOT_DAG_RUN_ID"
test -n "$TRAFFIC_FLOW_SNAPSHOT_DAG_RUN_ID"
export DBT_TRAFFIC_VARS="$(python3 -c 'import json, os; print(json.dumps({"traffic_snapshot_dag_run_id": os.environ["TRAFFIC_SNAPSHOT_DAG_RUN_ID"], "traffic_flow_snapshot_dag_run_id": os.environ["TRAFFIC_FLOW_SNAPSHOT_DAG_RUN_ID"]}))')"
export DBT_COMPILE_VARS='{"traffic_snapshot_dag_run_id":"compile_only__traffic_incident","traffic_flow_snapshot_dag_run_id":"compile_only__traffic_flow"}'
export DBT_PACKAGES_INSTALL_PATH=/tmp/asac-dbt-traffic-quality-gold-packages
~~~

DBT_COMPILE_VARS must never be passed to dbt run or dbt test.

---

### Task 1: Stage exact-five inventory and classify existing relations

**Files:**
- Create: domains/traffic_weather/tests/traffic/test_traffic_quality_gold_contract.py
- Modify: domains/traffic_weather/models/traffic/transform/gold/gold_traffic_incident_current_by_admin_dong_hourly.yml
- Modify: domains/traffic_weather/models/traffic/transform/gold/_gold.yml

**Interfaces:**
- Consumes: the existing current-hour, x-flow, and summary model metadata.
- Produces: one metadata-only test that can turn GREEN immediately and two exact-five tests that intentionally remain RED until Task 4.

- [ ] **Step 1: Write the staged contract test**

Create domains/traffic_weather/tests/traffic/test_traffic_quality_gold_contract.py with exactly:

~~~python
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR = PROJECT_ROOT / "models" / "traffic" / "transform" / "gold"
APPROVED_PRODUCTS = {
    "gold_traffic_incident_current_by_admin_dong_hourly",
    "gold_traffic_incident_x_flow",
    "gold_traffic_incident_collection_coverage_5m",
    "gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily",
    "gold_traffic_incident_spatial_mapping_quality_daily",
}
SUMMARY_MODEL = "gold_traffic_incident_summary"


def _gold_model_metadata() -> dict[str, dict]:
    models: dict[str, dict] = {}
    for path in sorted(GOLD_DIR.glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for model in document.get("models", []):
            name = model["name"]
            assert name not in models, f"duplicate Gold metadata for {name}"
            models[name] = model
    return models


def _meta(model: dict) -> dict:
    return model.get("config", {}).get("meta", {})


def test_existing_traffic_quality_gold_classification() -> None:
    models = _gold_model_metadata()

    assert _meta(
        models["gold_traffic_incident_current_by_admin_dong_hourly"]
    ).get("traffic_quality_product") is True
    assert _meta(models["gold_traffic_incident_x_flow"]).get(
        "traffic_quality_product"
    ) is True
    assert _meta(models[SUMMARY_MODEL]).get("traffic_quality_product") is False
    assert _meta(models[SUMMARY_MODEL]).get("support_only") is True


def test_traffic_quality_gold_metadata_ship_set_is_exactly_five() -> None:
    models = _gold_model_metadata()
    actual = {
        name
        for name, model in models.items()
        if _meta(model).get("traffic_quality_product") is True
    }

    assert actual == APPROVED_PRODUCTS
    assert SUMMARY_MODEL not in actual


def test_traffic_quality_gold_physical_ship_set_is_exactly_five() -> None:
    actual = {
        path.stem
        for path in GOLD_DIR.glob("gold_traffic_incident_*.sql")
        if path.stem != SUMMARY_MODEL
    }

    assert actual == APPROVED_PRODUCTS
~~~

- [ ] **Step 2: Run the initial RED checks**

Run:

~~~bash
python3 -m pytest domains/traffic_weather/tests/traffic/test_traffic_quality_gold_contract.py -q
~~~

Expected: 3 failed. Existing metadata has no traffic_quality_product/support_only flags, and the three new metadata entries and SQL files do not exist.

- [ ] **Step 3: Add only the existing-model classification metadata**

In domains/traffic_weather/models/traffic/transform/gold/gold_traffic_incident_current_by_admin_dong_hourly.yml, make traffic_quality_product a sibling of the existing public_gold metadata:

~~~yaml
    config:
      meta:
        traffic_quality_product: true
        public_gold:
~~~

In domains/traffic_weather/models/traffic/transform/gold/_gold.yml, replace the summary description and add its config exactly as follows:

~~~yaml
    description: Support-only one-row-per-source aggregate of the pinned current incident snapshot; excluded from the five Traffic Quality Gold products.
    config:
      meta:
        traffic_quality_product: false
        support_only: true
~~~

Add this exact config below the x-flow description:

~~~yaml
    config:
      meta:
        traffic_quality_product: true
~~~

Do not change either existing model SQL file.

- [ ] **Step 4: Verify the metadata-only test is GREEN**

Run:

~~~bash
python3 -m pytest domains/traffic_weather/tests/traffic/test_traffic_quality_gold_contract.py::test_existing_traffic_quality_gold_classification -q
~~~

Expected: 1 passed.

- [ ] **Step 5: Confirm exact-five inventory remains intentionally RED**

Run:

~~~bash
python3 -m pytest domains/traffic_weather/tests/traffic/test_traffic_quality_gold_contract.py::test_traffic_quality_gold_metadata_ship_set_is_exactly_five domains/traffic_weather/tests/traffic/test_traffic_quality_gold_contract.py::test_traffic_quality_gold_physical_ship_set_is_exactly_five -q
~~~

Expected: 2 failed. Do not require these tests to pass until all three new YAML entries and SQL files exist at the end of Task 4.

---

### Task 2: Add materialized request-audit coverage by collected 5-minute window

**Files:**
- Create: domains/traffic_weather/models/traffic/transform/gold/gold_traffic_incident_collection_coverage_5m.sql
- Modify: domains/traffic_weather/models/traffic/transform/gold/_gold.yml
- Create: domains/traffic_weather/tests/traffic/transform/gold/assert_gold_traffic_incident_collection_coverage_5m_grain_unique.sql
- Create: domains/traffic_weather/tests/traffic/transform/gold/assert_gold_traffic_incident_collection_coverage_5m_reconciles.sql

**Interfaces:**
- Consumes: source('traffic_bronze', 'seoul_traffic_incident_request_audit') and latest_manifest_run_state('traffic_bronze', 'collection_run_manifest', 'seoul_traffic_incident').
- Produces: observed audit windows only at source_id × coverage_window_at_utc, with evidence_scope fixed to materialized_snapshot_only. It does not consume traffic_snapshot_dag_run_id and does not create missing schedule windows.

- [ ] **Step 1: Write the failing grain and semantic test**

Create domains/traffic_weather/tests/traffic/transform/gold/assert_gold_traffic_incident_collection_coverage_5m_grain_unique.sql with exactly:

~~~sql
-- depends_on: {{ ref('gold_traffic_incident_collection_coverage_5m') }}

with checked as (
    select
        *,
        count(*) over (
            partition by source_id, coverage_window_at_utc
        ) as natural_grain_row_count,
        count(*) over (
            partition by product_row_id
        ) as product_row_id_row_count,
        case
            when effective_manifest_run_count <> observed_run_count
                then 'manifest_missing'
            when api_failed_request_count > 0
                then 'api_failure'
            when terminal_failure_run_count > 0
              or manifest_not_publishable_run_count > 0
              or success_publishable_run_count <> observed_run_count
                then 'manifest_not_publishable'
            when invalid_contract_request_count > 0
              or duplicate_request_count > 0
              or materialized_raw_object_count <> materialized_distinct_request_count
                then 'materialized_partial'
            when materialized_row_count = 0
                then 'materialized_zero'
            else 'materialized_consistent'
        end as expected_coverage_state
    from {{ ref('gold_traffic_incident_collection_coverage_5m') }}
)

select *
from checked
where product_row_id is null
   or source_id is null
   or source_id is distinct from 'seoul_traffic_incident'
   or coverage_window_at_utc is null
   or coverage_window_end_at_utc is distinct from date_add(
       'minute',
       5,
       coverage_window_at_utc
   )
   or coverage_window_at_utc is distinct from date_trunc(
       'minute',
       coverage_window_at_utc
   )
   or mod(minute(coverage_window_at_utc), 5) <> 0
   or evidence_scope is distinct from 'materialized_snapshot_only'
   or natural_grain_row_count <> 1
   or product_row_id_row_count <> 1
   or product_row_id is distinct from concat(
       source_id,
       '|',
       to_iso8601(cast(coverage_window_at_utc as timestamp(6)))
   )
   or materialized_request_count <= 0
   or materialized_distinct_request_count < 0
   or materialized_distinct_request_count > materialized_request_count
   or duplicate_request_count is distinct from (
       materialized_request_count - materialized_distinct_request_count
   )
   or materialized_raw_object_count < 0
   or materialized_row_count < 0
   or successful_request_count < 0
   or api_failed_request_count < 0
   or successful_request_count + api_failed_request_count
       > materialized_request_count
   or invalid_contract_request_count < 0
   or observed_run_count < 0
   or effective_manifest_run_count < 0
   or effective_manifest_run_count > observed_run_count
   or success_publishable_run_count < 0
   or success_publishable_run_count > effective_manifest_run_count
   or terminal_failure_run_count < 0
   or terminal_failure_run_count > effective_manifest_run_count
   or manifest_not_publishable_run_count < 0
   or manifest_not_publishable_run_count > effective_manifest_run_count
   or first_collected_at_utc is null
   or last_collected_at_utc is null
   or first_collected_at_utc > last_collected_at_utc
   or coverage_state is distinct from expected_coverage_state
~~~

- [ ] **Step 2: Write the failing source reconciliation test**

Create domains/traffic_weather/tests/traffic/transform/gold/assert_gold_traffic_incident_collection_coverage_5m_reconciles.sql with exactly:

~~~sql
-- depends_on: {{ ref('gold_traffic_incident_collection_coverage_5m') }}

with latest_manifest_state as (
    {{ latest_manifest_run_state('traffic_bronze', 'collection_run_manifest', 'seoul_traffic_incident') }}
),

windowed_audit as (
    select
        cast(audit.request_id as varchar) as request_id,
        cast(audit.source_id as varchar) as source_id,
        try_cast(audit.start_index as integer) as start_index,
        try_cast(audit.end_index as integer) as end_index,
        cast(audit.request_params_json as varchar) as request_params_json,
        cast(audit.raw_object_key as varchar) as raw_object_key,
        cast(audit.payload_hash as varchar) as payload_hash,
        try_cast(audit.http_status as integer) as http_status,
        cast(audit.result_code as varchar) as result_code,
        cast(audit.result_msg as varchar) as result_msg,
        try_cast(audit.list_total_count as integer) as list_total_count,
        try_cast(audit.row_count as bigint) as row_count,
        cast(audit.collected_at as timestamp(6)) as collected_at,
        cast(audit.load_date as varchar) as load_date,
        cast(audit.dag_run_id as varchar) as dag_run_id,
        date_add(
            'minute',
            -mod(minute(cast(audit.collected_at as timestamp(6))), 5),
            date_trunc('minute', cast(audit.collected_at as timestamp(6)))
        ) as coverage_window_at_utc
    from {{ source('traffic_bronze', 'seoul_traffic_incident_request_audit') }} as audit
),

audit_with_manifest as (
    select
        audit.*,
        manifest.dag_run_id as effective_manifest_dag_run_id,
        manifest.manifest_status,
        manifest.is_publishable,
        manifest.manifest_failure_reason
    from windowed_audit as audit
    left join latest_manifest_state as manifest
        on audit.source_id = manifest.source_id
       and audit.dag_run_id = manifest.dag_run_id
),

evidence as (
    select
        source_id,
        coverage_window_at_utc,
        count(*) as materialized_request_count,
        count(distinct request_id) as materialized_distinct_request_count,
        count(*) - count(distinct request_id) as duplicate_request_count,
        count(distinct raw_object_key) as materialized_raw_object_count,
        coalesce(sum(row_count), cast(0 as bigint)) as materialized_row_count,
        count_if(
            http_status between 200 and 299
            and result_code = 'INFO-000'
        ) as successful_request_count,
        count_if(
            (http_status is not null and not (http_status between 200 and 299))
            or (result_code is not null and result_code <> 'INFO-000')
        ) as api_failed_request_count,
        count_if(
            request_id is null
            or source_id is null
            or source_id <> 'seoul_traffic_incident'
            or request_params_json is null
            or start_index is null
            or start_index <= 0
            or end_index is null
            or end_index < start_index
            or raw_object_key is null
            or payload_hash is null
            or http_status is null
            or result_code is null
            or result_msg is null
            or list_total_count is null
            or list_total_count < 0
            or row_count is null
            or row_count < 0
            or collected_at is null
            or load_date is null
            or dag_run_id is null
        ) as invalid_contract_request_count,
        count(distinct dag_run_id) as observed_run_count,
        count(distinct effective_manifest_dag_run_id)
            as effective_manifest_run_count,
        count(
            distinct case
                when manifest_status = 'SUCCESS'
                 and coalesce(is_publishable, false)
                    then effective_manifest_dag_run_id
            end
        ) as success_publishable_run_count,
        count(
            distinct case
                when manifest_status = 'FAILED'
                  or nullif(
                      trim(coalesce(manifest_failure_reason, '')),
                      ''
                  ) is not null
                    then effective_manifest_dag_run_id
            end
        ) as terminal_failure_run_count,
        count(
            distinct case
                when effective_manifest_dag_run_id is not null
                 and (
                     manifest_status is distinct from 'SUCCESS'
                     or not coalesce(is_publishable, false)
                 )
                    then effective_manifest_dag_run_id
            end
        ) as manifest_not_publishable_run_count,
        min(list_total_count) as min_reported_incident_count,
        max(list_total_count) as max_reported_incident_count,
        min(collected_at) as first_collected_at_utc,
        max(collected_at) as last_collected_at_utc
    from audit_with_manifest
    group by source_id, coverage_window_at_utc
),

expected as (
    select
        concat(
            source_id,
            '|',
            to_iso8601(cast(coverage_window_at_utc as timestamp(6)))
        ) as product_row_id,
        source_id,
        coverage_window_at_utc,
        date_add('minute', 5, coverage_window_at_utc)
            as coverage_window_end_at_utc,
        cast('materialized_snapshot_only' as varchar) as evidence_scope,
        materialized_request_count,
        materialized_distinct_request_count,
        duplicate_request_count,
        materialized_raw_object_count,
        materialized_row_count,
        successful_request_count,
        api_failed_request_count,
        invalid_contract_request_count,
        observed_run_count,
        effective_manifest_run_count,
        success_publishable_run_count,
        terminal_failure_run_count,
        manifest_not_publishable_run_count,
        min_reported_incident_count,
        max_reported_incident_count,
        first_collected_at_utc,
        last_collected_at_utc,
        case
            when effective_manifest_run_count <> observed_run_count
                then 'manifest_missing'
            when api_failed_request_count > 0
                then 'api_failure'
            when terminal_failure_run_count > 0
              or manifest_not_publishable_run_count > 0
              or success_publishable_run_count <> observed_run_count
                then 'manifest_not_publishable'
            when invalid_contract_request_count > 0
              or duplicate_request_count > 0
              or materialized_raw_object_count <> materialized_distinct_request_count
                then 'materialized_partial'
            when materialized_row_count = 0
                then 'materialized_zero'
            else 'materialized_consistent'
        end as coverage_state
    from evidence
),

actual as (
    select
        product_row_id,
        source_id,
        coverage_window_at_utc,
        coverage_window_end_at_utc,
        evidence_scope,
        materialized_request_count,
        materialized_distinct_request_count,
        duplicate_request_count,
        materialized_raw_object_count,
        materialized_row_count,
        successful_request_count,
        api_failed_request_count,
        invalid_contract_request_count,
        observed_run_count,
        effective_manifest_run_count,
        success_publishable_run_count,
        terminal_failure_run_count,
        manifest_not_publishable_run_count,
        min_reported_incident_count,
        max_reported_incident_count,
        first_collected_at_utc,
        last_collected_at_utc,
        coverage_state
    from {{ ref('gold_traffic_incident_collection_coverage_5m') }}
),

missing_rows as (
    select * from expected
    except
    select * from actual
),

extra_rows as (
    select * from actual
    except
    select * from expected
)

select 'missing_expected_row' as violation_type, *
from missing_rows

union all

select 'extra_actual_row' as violation_type, *
from extra_rows
~~~

- [ ] **Step 3: Install dependencies outside the worktree and run the RED parse**

Run:

~~~bash
dbt --log-path /tmp/asac-dbt-traffic-quality-gold-logs deps --project-dir domains/traffic_weather --profiles-dir domains/traffic_weather
dbt --log-path /tmp/asac-dbt-traffic-quality-gold-logs parse --project-dir domains/traffic_weather --profiles-dir domains/traffic_weather --target dev --no-partial-parse --target-path /tmp/asac-dbt-traffic-quality-gold-red-coverage --vars "$DBT_COMPILE_VARS"
~~~

Expected: dependency install PASS, then parse FAIL because both singular tests ref a model node that does not exist.

- [ ] **Step 4: Implement the complete coverage model**

Create domains/traffic_weather/models/traffic/transform/gold/gold_traffic_incident_collection_coverage_5m.sql with exactly:

~~~sql
-- Materialized request-audit evidence by observed collected 5-minute window.
-- This is not a schedule lattice: windows with no landed audit row do not exist.

{{ config(materialized='table') }}

with latest_manifest_state as (
    {{ latest_manifest_run_state('traffic_bronze', 'collection_run_manifest', 'seoul_traffic_incident') }}
),

windowed_audit as (
    select
        cast(audit.request_id as varchar) as request_id,
        cast(audit.source_id as varchar) as source_id,
        try_cast(audit.start_index as integer) as start_index,
        try_cast(audit.end_index as integer) as end_index,
        cast(audit.request_params_json as varchar) as request_params_json,
        cast(audit.raw_object_key as varchar) as raw_object_key,
        cast(audit.payload_hash as varchar) as payload_hash,
        try_cast(audit.http_status as integer) as http_status,
        cast(audit.result_code as varchar) as result_code,
        cast(audit.result_msg as varchar) as result_msg,
        try_cast(audit.list_total_count as integer) as list_total_count,
        try_cast(audit.row_count as bigint) as row_count,
        cast(audit.collected_at as timestamp(6)) as collected_at,
        cast(audit.load_date as varchar) as load_date,
        cast(audit.dag_run_id as varchar) as dag_run_id,
        date_add(
            'minute',
            -mod(minute(cast(audit.collected_at as timestamp(6))), 5),
            date_trunc('minute', cast(audit.collected_at as timestamp(6)))
        ) as coverage_window_at_utc
    from {{ source('traffic_bronze', 'seoul_traffic_incident_request_audit') }} as audit
),

audit_with_manifest as (
    select
        audit.*,
        manifest.dag_run_id as effective_manifest_dag_run_id,
        manifest.manifest_status,
        manifest.is_publishable,
        manifest.manifest_failure_reason
    from windowed_audit as audit
    left join latest_manifest_state as manifest
        on audit.source_id = manifest.source_id
       and audit.dag_run_id = manifest.dag_run_id
),

window_evidence as (
    select
        source_id,
        coverage_window_at_utc,
        count(*) as materialized_request_count,
        count(distinct request_id) as materialized_distinct_request_count,
        count(*) - count(distinct request_id) as duplicate_request_count,
        count(distinct raw_object_key) as materialized_raw_object_count,
        coalesce(sum(row_count), cast(0 as bigint)) as materialized_row_count,
        count_if(
            http_status between 200 and 299
            and result_code = 'INFO-000'
        ) as successful_request_count,
        count_if(
            (http_status is not null and not (http_status between 200 and 299))
            or (result_code is not null and result_code <> 'INFO-000')
        ) as api_failed_request_count,
        count_if(
            request_id is null
            or source_id is null
            or source_id <> 'seoul_traffic_incident'
            or request_params_json is null
            or start_index is null
            or start_index <= 0
            or end_index is null
            or end_index < start_index
            or raw_object_key is null
            or payload_hash is null
            or http_status is null
            or result_code is null
            or result_msg is null
            or list_total_count is null
            or list_total_count < 0
            or row_count is null
            or row_count < 0
            or collected_at is null
            or load_date is null
            or dag_run_id is null
        ) as invalid_contract_request_count,
        count(distinct dag_run_id) as observed_run_count,
        count(distinct effective_manifest_dag_run_id)
            as effective_manifest_run_count,
        count(
            distinct case
                when manifest_status = 'SUCCESS'
                 and coalesce(is_publishable, false)
                    then effective_manifest_dag_run_id
            end
        ) as success_publishable_run_count,
        count(
            distinct case
                when manifest_status = 'FAILED'
                  or nullif(
                      trim(coalesce(manifest_failure_reason, '')),
                      ''
                  ) is not null
                    then effective_manifest_dag_run_id
            end
        ) as terminal_failure_run_count,
        count(
            distinct case
                when effective_manifest_dag_run_id is not null
                 and (
                     manifest_status is distinct from 'SUCCESS'
                     or not coalesce(is_publishable, false)
                 )
                    then effective_manifest_dag_run_id
            end
        ) as manifest_not_publishable_run_count,
        min(list_total_count) as min_reported_incident_count,
        max(list_total_count) as max_reported_incident_count,
        min(collected_at) as first_collected_at_utc,
        max(collected_at) as last_collected_at_utc
    from audit_with_manifest
    group by source_id, coverage_window_at_utc
)

select
    concat(
        source_id,
        '|',
        to_iso8601(cast(coverage_window_at_utc as timestamp(6)))
    ) as product_row_id,
    source_id,
    coverage_window_at_utc,
    date_add('minute', 5, coverage_window_at_utc)
        as coverage_window_end_at_utc,
    cast('materialized_snapshot_only' as varchar) as evidence_scope,
    materialized_request_count,
    materialized_distinct_request_count,
    duplicate_request_count,
    materialized_raw_object_count,
    materialized_row_count,
    successful_request_count,
    api_failed_request_count,
    invalid_contract_request_count,
    observed_run_count,
    effective_manifest_run_count,
    success_publishable_run_count,
    terminal_failure_run_count,
    manifest_not_publishable_run_count,
    min_reported_incident_count,
    max_reported_incident_count,
    first_collected_at_utc,
    last_collected_at_utc,
    case
        when effective_manifest_run_count <> observed_run_count
            then 'manifest_missing'
        when api_failed_request_count > 0
            then 'api_failure'
        when terminal_failure_run_count > 0
          or manifest_not_publishable_run_count > 0
          or success_publishable_run_count <> observed_run_count
            then 'manifest_not_publishable'
        when invalid_contract_request_count > 0
          or duplicate_request_count > 0
          or materialized_raw_object_count <> materialized_distinct_request_count
            then 'materialized_partial'
        when materialized_row_count = 0
            then 'materialized_zero'
        else 'materialized_consistent'
    end as coverage_state
from window_evidence
~~~

- [ ] **Step 5: Add the complete coverage YAML entry**

Append this model entry to domains/traffic_weather/models/traffic/transform/gold/_gold.yml:

~~~yaml
  - name: gold_traffic_incident_collection_coverage_5m
    description: 실제로 물질화된 TOPIS request-audit를 source와 UTC 수집 5분 구간별로 요약하며 미착륙 schedule slot은 생성하지 않는 품질 제품입니다.
    config:
      meta:
        traffic_quality_product: true
    columns:
      - name: product_row_id
        description: source_id와 coverage_window_at_utc를 결정적으로 직렬화한 식별자입니다.
        tests: [not_null, unique]
      - name: source_id
        description: request-audit source identifier입니다.
        tests: [not_null]
      - name: coverage_window_at_utc
        description: collected_at을 UTC-naive 5분 경계로 내림한 관측 구간 시작입니다.
        tests: [not_null]
      - name: coverage_window_end_at_utc
        description: 관측 구간의 exclusive 종료 시각입니다.
        tests: [not_null]
      - name: evidence_scope
        description: 이 제품이 물질화된 snapshot 증거만 표현함을 나타냅니다.
        tests:
          - not_null
          - accepted_values:
              arguments:
                values: ['materialized_snapshot_only']
      - name: materialized_request_count
        description: 해당 구간에 실제 존재하는 audit row 수입니다.
        tests: [not_null]
      - name: materialized_distinct_request_count
        description: 해당 구간의 distinct request_id 수입니다.
        tests: [not_null]
      - name: duplicate_request_count
        description: materialized request row 수와 distinct request 수의 차이입니다.
        tests: [not_null]
      - name: materialized_raw_object_count
        description: audit가 가리키는 distinct raw_object_key 수입니다.
        tests: [not_null]
      - name: materialized_row_count
        description: audit row_count의 합이며 schedule 기대량이 아닙니다.
        tests: [not_null]
      - name: successful_request_count
        description: HTTP 2xx이며 result_code가 INFO-000인 audit request 수입니다.
        tests: [not_null]
      - name: api_failed_request_count
        description: non-2xx 또는 non-INFO-000인 audit request 수입니다.
        tests: [not_null]
      - name: invalid_contract_request_count
        description: 필수 request-audit 열 또는 page/count 계약을 위반한 row 수입니다.
        tests: [not_null]
      - name: observed_run_count
        description: audit row에서 관측한 distinct dag_run_id 수입니다.
        tests: [not_null]
      - name: effective_manifest_run_count
        description: source/run별 latest effective manifest에 결합된 distinct run 수입니다.
        tests: [not_null]
      - name: success_publishable_run_count
        description: latest effective 상태가 SUCCESS와 publishable인 distinct run 수입니다.
        tests: [not_null]
      - name: terminal_failure_run_count
        description: latest effective 상태가 FAILED이거나 failure reason이 있는 distinct run 수입니다.
        tests: [not_null]
      - name: manifest_not_publishable_run_count
        description: latest effective 상태가 SUCCESS+publishable이 아닌 distinct manifest run 수입니다.
        tests: [not_null]
      - name: min_reported_incident_count
        description: 구간 audit의 최소 list_total_count입니다.
      - name: max_reported_incident_count
        description: 구간 audit의 최대 list_total_count입니다.
      - name: first_collected_at_utc
        description: 구간에서 가장 이른 audit collected_at입니다.
        tests: [not_null]
      - name: last_collected_at_utc
        description: 구간에서 가장 늦은 audit collected_at입니다.
        tests: [not_null]
      - name: coverage_state
        description: 물질화된 audit와 latest effective manifest 정합 상태입니다.
        tests:
          - not_null
          - accepted_values:
              arguments:
                values:
                  - manifest_missing
                  - api_failure
                  - manifest_not_publishable
                  - materialized_partial
                  - materialized_zero
                  - materialized_consistent
~~~

- [ ] **Step 6: Run compile-only GREEN with synthetic vars**

Run:

~~~bash
dbt --log-path /tmp/asac-dbt-traffic-quality-gold-logs parse --project-dir domains/traffic_weather --profiles-dir domains/traffic_weather --target dev --no-partial-parse --target-path /tmp/asac-dbt-traffic-quality-gold-parse-coverage --vars "$DBT_COMPILE_VARS"
dbt --log-path /tmp/asac-dbt-traffic-quality-gold-logs compile --project-dir domains/traffic_weather --profiles-dir domains/traffic_weather --target dev --select gold_traffic_incident_collection_coverage_5m assert_gold_traffic_incident_collection_coverage_5m_grain_unique assert_gold_traffic_incident_collection_coverage_5m_reconciles --target-path /tmp/asac-dbt-traffic-quality-gold-compile-coverage --vars "$DBT_COMPILE_VARS"
~~~

Expected: both commands PASS. This proves graph and SQL compilation only.

- [ ] **Step 7: Run dev runtime GREEN with actual latest-run vars**

Run:

~~~bash
dbt --log-path /tmp/asac-dbt-traffic-quality-gold-logs run --project-dir domains/traffic_weather --profiles-dir domains/traffic_weather --target dev --select gold_traffic_incident_collection_coverage_5m --target-path /tmp/asac-dbt-traffic-quality-gold-run-coverage --vars "$DBT_TRAFFIC_VARS"
dbt --log-path /tmp/asac-dbt-traffic-quality-gold-logs test --project-dir domains/traffic_weather --profiles-dir domains/traffic_weather --target dev --select assert_gold_traffic_incident_collection_coverage_5m_grain_unique assert_gold_traffic_incident_collection_coverage_5m_reconciles --target-path /tmp/asac-dbt-traffic-quality-gold-test-coverage --vars "$DBT_TRAFFIC_VARS"
~~~

Expected: model run PASS and both singular tests PASS. No synthetic run ID is used for runtime validation.

- [ ] **Step 8: Confirm exact-five inventory remains RED for two missing products**

Run:

~~~bash
python3 -m pytest domains/traffic_weather/tests/traffic/test_traffic_quality_gold_contract.py::test_traffic_quality_gold_metadata_ship_set_is_exactly_five domains/traffic_weather/tests/traffic/test_traffic_quality_gold_contract.py::test_traffic_quality_gold_physical_ship_set_is_exactly_five -q
~~~

Expected: 2 failed because the expected-clearance and spatial-quality model/YAML entries do not exist yet.

---

### Task 3: Add expected-clearance evidence profile by occurrence day and mapping bucket

**Files:**
- Create: domains/traffic_weather/models/traffic/transform/gold/gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily.sql
- Modify: domains/traffic_weather/models/traffic/transform/gold/_gold.yml
- Create: domains/traffic_weather/tests/traffic/transform/gold/assert_gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily_grain_unique.sql
- Create: domains/traffic_weather/tests/traffic/transform/gold/assert_gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily_reconciles.sql

**Interfaces:**
- Consumes: ref('silver_seoul_traffic_incident_current') and ref('asac_axes', 'dim_admin_dong'). The current relation inherits the exact traffic_snapshot_dag_run_id pin.
- Produces: profile_day × mapping_bucket rows including incidents whose expected_clear_at is null. Lead minutes are source-provided expectations, never actual duration.

- [ ] **Step 1: Write the failing grain and metric semantics test**

Create domains/traffic_weather/tests/traffic/transform/gold/assert_gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily_grain_unique.sql with exactly:

~~~sql
-- depends_on: {{ ref('gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily') }}

{% set snapshot_dag_run_id = var('traffic_snapshot_dag_run_id') %}

with checked as (
    select
        *,
        count(*) over (
            partition by profile_day, mapping_bucket
        ) as natural_grain_row_count,
        count(*) over (
            partition by product_row_id
        ) as product_row_id_row_count,
        case
            when expected_clearance_present_count = 0
                then 'no_expected_clearance_evidence'
            when expected_clearance_usable_count = 0
             and expected_clearance_invalid_count > 0
                then 'invalid_expected_clearance_evidence'
            when expected_clearance_missing_count > 0
              or expected_clearance_invalid_count > 0
                then 'partial_expected_clearance_evidence'
            else 'complete_expected_clearance_evidence'
        end as expected_profile_state
    from {{ ref('gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily') }}
)

select *
from checked
where product_row_id is null
   or profile_day is null
   or mapping_bucket is null
   or snapshot_dag_run_id is null
   or snapshot_dag_run_id is distinct from '{{ snapshot_dag_run_id | replace("'", "''") }}'
   or snapshot_run_count <> 1
   or evidence_scope is distinct from 'pinned_current_snapshot_by_occurrence_day'
   or natural_grain_row_count <> 1
   or product_row_id_row_count <> 1
   or product_row_id is distinct from concat(
       cast(profile_day as varchar),
       '|',
       mapping_bucket
   )
   or incident_count <= 0
   or expected_clearance_present_count < 0
   or expected_clearance_missing_count < 0
   or expected_clearance_usable_count < 0
   or expected_clearance_invalid_count < 0
   or incident_count is distinct from (
       expected_clearance_present_count + expected_clearance_missing_count
   )
   or expected_clearance_present_count is distinct from (
       expected_clearance_usable_count + expected_clearance_invalid_count
   )
   or abs(
       expected_clearance_present_ratio
       - cast(expected_clearance_present_count as double)
         / cast(incident_count as double)
   ) > 0.000000000001
   or abs(
       expected_clearance_missing_ratio
       - cast(expected_clearance_missing_count as double)
         / cast(incident_count as double)
   ) > 0.000000000001
   or abs(
       expected_clearance_usable_ratio
       - cast(expected_clearance_usable_count as double)
         / cast(incident_count as double)
   ) > 0.000000000001
   or abs(
       expected_clearance_invalid_ratio
       - cast(expected_clearance_invalid_count as double)
         / cast(incident_count as double)
   ) > 0.000000000001
   or (
       expected_clearance_usable_count = 0
       and (
           min_expected_clearance_lead_minutes is not null
           or avg_expected_clearance_lead_minutes is not null
           or max_expected_clearance_lead_minutes is not null
       )
   )
   or (
       expected_clearance_usable_count > 0
       and (
           min_expected_clearance_lead_minutes is null
           or avg_expected_clearance_lead_minutes is null
           or max_expected_clearance_lead_minutes is null
           or min_expected_clearance_lead_minutes < 0
           or min_expected_clearance_lead_minutes
               > avg_expected_clearance_lead_minutes
           or avg_expected_clearance_lead_minutes
               > max_expected_clearance_lead_minutes
       )
   )
   or profile_state is distinct from expected_profile_state
   or (
       mapping_bucket = '__UNMAPPED__'
       and (
           admin_dong_code is not null
           or admin_dong is not null
           or gu_code is not null
           or gu is not null
           or admin_dong_revision_date is not null
       )
   )
   or (
       mapping_bucket <> '__UNMAPPED__'
       and (
           admin_dong_code is distinct from mapping_bucket
           or admin_dong is null
           or gu_code is null
           or gu is null
           or admin_dong_revision_date is null
       )
   )
~~~

- [ ] **Step 2: Write the failing source reconciliation test**

Create domains/traffic_weather/tests/traffic/transform/gold/assert_gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily_reconciles.sql with exactly:

~~~sql
-- depends_on: {{ ref('gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily') }}
-- depends_on: {{ ref('silver_seoul_traffic_incident_current') }}
-- depends_on: {{ ref('asac_axes', 'dim_admin_dong') }}

with canonical_raw as (
    select
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(admin_dong as varchar) as admin_dong,
        cast(gu_code as varchar) as gu_code,
        cast(gu as varchar) as gu,
        try_cast(revision_date as date) as admin_dong_revision_date
    from {{ ref('asac_axes', 'dim_admin_dong') }}
),

canonical_ranked as (
    select
        *,
        row_number() over (
            partition by admin_dong_code
            order by
                admin_dong_revision_date desc nulls last,
                admin_dong asc nulls last,
                gu_code asc nulls last,
                gu asc nulls last
        ) as canonical_row_num
    from canonical_raw
),

canonical as (
    select *
    from canonical_ranked
    where admin_dong_code is not null
      and canonical_row_num = 1
),

classified as (
    select
        cast(current_snapshot.occurred_at as date) as profile_day,
        coalesce(canonical.admin_dong_code, '__UNMAPPED__') as mapping_bucket,
        canonical.admin_dong_code,
        canonical.admin_dong,
        canonical.gu_code,
        canonical.gu,
        canonical.admin_dong_revision_date,
        cast(current_snapshot.dag_run_id as varchar) as snapshot_dag_run_id,
        cast(current_snapshot.occurred_at as timestamp(6)) as occurred_at,
        cast(current_snapshot.expected_clear_at as timestamp(6))
            as expected_clear_at,
        case
            when current_snapshot.expected_clear_at
                >= current_snapshot.occurred_at
                then date_diff(
                    'minute',
                    current_snapshot.occurred_at,
                    current_snapshot.expected_clear_at
                )
        end as expected_clearance_lead_minutes
    from {{ ref('silver_seoul_traffic_incident_current') }} as current_snapshot
    left join canonical
        on cast(current_snapshot.admin_dong_code as varchar)
            = canonical.admin_dong_code
    where current_snapshot.occurred_at is not null
),

evidence as (
    select
        profile_day,
        mapping_bucket,
        admin_dong_code,
        admin_dong,
        gu_code,
        gu,
        admin_dong_revision_date,
        max(snapshot_dag_run_id) as snapshot_dag_run_id,
        count(distinct snapshot_dag_run_id) as snapshot_run_count,
        count(*) as incident_count,
        count_if(expected_clear_at is not null)
            as expected_clearance_present_count,
        count_if(expected_clear_at is null)
            as expected_clearance_missing_count,
        count_if(expected_clear_at >= occurred_at)
            as expected_clearance_usable_count,
        count_if(expected_clear_at < occurred_at)
            as expected_clearance_invalid_count,
        min(expected_clearance_lead_minutes)
            as min_expected_clearance_lead_minutes,
        avg(cast(expected_clearance_lead_minutes as double))
            as avg_expected_clearance_lead_minutes,
        max(expected_clearance_lead_minutes)
            as max_expected_clearance_lead_minutes
    from classified
    group by
        profile_day,
        mapping_bucket,
        admin_dong_code,
        admin_dong,
        gu_code,
        gu,
        admin_dong_revision_date
),

expected as (
    select
        concat(cast(profile_day as varchar), '|', mapping_bucket)
            as product_row_id,
        profile_day,
        mapping_bucket,
        admin_dong_code,
        admin_dong,
        gu_code,
        gu,
        admin_dong_revision_date,
        snapshot_dag_run_id,
        snapshot_run_count,
        cast('pinned_current_snapshot_by_occurrence_day' as varchar)
            as evidence_scope,
        incident_count,
        expected_clearance_present_count,
        expected_clearance_missing_count,
        expected_clearance_usable_count,
        expected_clearance_invalid_count,
        cast(expected_clearance_present_count as double)
            / cast(incident_count as double)
            as expected_clearance_present_ratio,
        cast(expected_clearance_missing_count as double)
            / cast(incident_count as double)
            as expected_clearance_missing_ratio,
        cast(expected_clearance_usable_count as double)
            / cast(incident_count as double)
            as expected_clearance_usable_ratio,
        cast(expected_clearance_invalid_count as double)
            / cast(incident_count as double)
            as expected_clearance_invalid_ratio,
        min_expected_clearance_lead_minutes,
        avg_expected_clearance_lead_minutes,
        max_expected_clearance_lead_minutes,
        case
            when expected_clearance_present_count = 0
                then 'no_expected_clearance_evidence'
            when expected_clearance_usable_count = 0
             and expected_clearance_invalid_count > 0
                then 'invalid_expected_clearance_evidence'
            when expected_clearance_missing_count > 0
              or expected_clearance_invalid_count > 0
                then 'partial_expected_clearance_evidence'
            else 'complete_expected_clearance_evidence'
        end as profile_state
    from evidence
),

actual as (
    select
        product_row_id,
        profile_day,
        mapping_bucket,
        admin_dong_code,
        admin_dong,
        gu_code,
        gu,
        admin_dong_revision_date,
        snapshot_dag_run_id,
        snapshot_run_count,
        evidence_scope,
        incident_count,
        expected_clearance_present_count,
        expected_clearance_missing_count,
        expected_clearance_usable_count,
        expected_clearance_invalid_count,
        expected_clearance_present_ratio,
        expected_clearance_missing_ratio,
        expected_clearance_usable_ratio,
        expected_clearance_invalid_ratio,
        min_expected_clearance_lead_minutes,
        avg_expected_clearance_lead_minutes,
        max_expected_clearance_lead_minutes,
        profile_state
    from {{ ref('gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily') }}
),

missing_rows as (
    select * from expected
    except
    select * from actual
),

extra_rows as (
    select * from actual
    except
    select * from expected
)

select 'missing_expected_row' as violation_type, *
from missing_rows

union all

select 'extra_actual_row' as violation_type, *
from extra_rows
~~~

- [ ] **Step 3: Run the RED parse**

Run:

~~~bash
dbt --log-path /tmp/asac-dbt-traffic-quality-gold-logs parse --project-dir domains/traffic_weather --profiles-dir domains/traffic_weather --target dev --no-partial-parse --target-path /tmp/asac-dbt-traffic-quality-gold-red-clearance --vars "$DBT_COMPILE_VARS"
~~~

Expected: FAIL because both singular tests ref the absent expected-clearance model.

- [ ] **Step 4: Implement the complete expected-clearance model**

Create domains/traffic_weather/models/traffic/transform/gold/gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily.sql with exactly:

~~~sql
-- Expected-clearance evidence among incidents present in the pinned current snapshot.
-- Lead minutes are source-provided expectations, not observed resolution duration.
-- depends_on: {{ ref('silver_seoul_traffic_incident_current') }}
-- depends_on: {{ ref('asac_axes', 'dim_admin_dong') }}

{{ config(materialized='table') }}

with canonical_raw as (
    select
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(admin_dong as varchar) as admin_dong,
        cast(gu_code as varchar) as gu_code,
        cast(gu as varchar) as gu,
        try_cast(revision_date as date) as admin_dong_revision_date
    from {{ ref('asac_axes', 'dim_admin_dong') }}
),

canonical_ranked as (
    select
        *,
        row_number() over (
            partition by admin_dong_code
            order by
                admin_dong_revision_date desc nulls last,
                admin_dong asc nulls last,
                gu_code asc nulls last,
                gu asc nulls last
        ) as canonical_row_num
    from canonical_raw
),

canonical as (
    select *
    from canonical_ranked
    where admin_dong_code is not null
      and canonical_row_num = 1
),

classified as (
    select
        cast(current_snapshot.occurred_at as date) as profile_day,
        coalesce(canonical.admin_dong_code, '__UNMAPPED__') as mapping_bucket,
        canonical.admin_dong_code,
        canonical.admin_dong,
        canonical.gu_code,
        canonical.gu,
        canonical.admin_dong_revision_date,
        cast(current_snapshot.dag_run_id as varchar) as snapshot_dag_run_id,
        cast(current_snapshot.occurred_at as timestamp(6)) as occurred_at,
        cast(current_snapshot.expected_clear_at as timestamp(6))
            as expected_clear_at,
        case
            when current_snapshot.expected_clear_at
                >= current_snapshot.occurred_at
                then date_diff(
                    'minute',
                    current_snapshot.occurred_at,
                    current_snapshot.expected_clear_at
                )
        end as expected_clearance_lead_minutes
    from {{ ref('silver_seoul_traffic_incident_current') }} as current_snapshot
    left join canonical
        on cast(current_snapshot.admin_dong_code as varchar)
            = canonical.admin_dong_code
    where current_snapshot.occurred_at is not null
),

profile_evidence as (
    select
        profile_day,
        mapping_bucket,
        admin_dong_code,
        admin_dong,
        gu_code,
        gu,
        admin_dong_revision_date,
        max(snapshot_dag_run_id) as snapshot_dag_run_id,
        count(distinct snapshot_dag_run_id) as snapshot_run_count,
        count(*) as incident_count,
        count_if(expected_clear_at is not null)
            as expected_clearance_present_count,
        count_if(expected_clear_at is null)
            as expected_clearance_missing_count,
        count_if(expected_clear_at >= occurred_at)
            as expected_clearance_usable_count,
        count_if(expected_clear_at < occurred_at)
            as expected_clearance_invalid_count,
        min(expected_clearance_lead_minutes)
            as min_expected_clearance_lead_minutes,
        avg(cast(expected_clearance_lead_minutes as double))
            as avg_expected_clearance_lead_minutes,
        max(expected_clearance_lead_minutes)
            as max_expected_clearance_lead_minutes
    from classified
    group by
        profile_day,
        mapping_bucket,
        admin_dong_code,
        admin_dong,
        gu_code,
        gu,
        admin_dong_revision_date
)

select
    concat(cast(profile_day as varchar), '|', mapping_bucket)
        as product_row_id,
    profile_day,
    mapping_bucket,
    admin_dong_code,
    admin_dong,
    gu_code,
    gu,
    admin_dong_revision_date,
    snapshot_dag_run_id,
    snapshot_run_count,
    cast('pinned_current_snapshot_by_occurrence_day' as varchar)
        as evidence_scope,
    incident_count,
    expected_clearance_present_count,
    expected_clearance_missing_count,
    expected_clearance_usable_count,
    expected_clearance_invalid_count,
    cast(expected_clearance_present_count as double)
        / cast(incident_count as double)
        as expected_clearance_present_ratio,
    cast(expected_clearance_missing_count as double)
        / cast(incident_count as double)
        as expected_clearance_missing_ratio,
    cast(expected_clearance_usable_count as double)
        / cast(incident_count as double)
        as expected_clearance_usable_ratio,
    cast(expected_clearance_invalid_count as double)
        / cast(incident_count as double)
        as expected_clearance_invalid_ratio,
    min_expected_clearance_lead_minutes,
    avg_expected_clearance_lead_minutes,
    max_expected_clearance_lead_minutes,
    case
        when expected_clearance_present_count = 0
            then 'no_expected_clearance_evidence'
        when expected_clearance_usable_count = 0
         and expected_clearance_invalid_count > 0
            then 'invalid_expected_clearance_evidence'
        when expected_clearance_missing_count > 0
          or expected_clearance_invalid_count > 0
            then 'partial_expected_clearance_evidence'
        else 'complete_expected_clearance_evidence'
    end as profile_state
from profile_evidence
~~~

- [ ] **Step 5: Add the complete expected-clearance YAML entry**

Append this model entry to domains/traffic_weather/models/traffic/transform/gold/_gold.yml:

~~~yaml
  - name: gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily
    description: 고정 current snapshot의 incident를 발생일과 canonical 또는 unmapped bucket으로 묶어 expected-clear 증거 비율과 예상 lead minutes를 제공하는 제품입니다.
    config:
      meta:
        traffic_quality_product: true
    columns:
      - name: product_row_id
        description: profile_day와 mapping_bucket의 결정적 식별자입니다.
        tests: [not_null, unique]
      - name: profile_day
        description: occurred_at의 KST calendar date입니다.
        tests: [not_null]
      - name: mapping_bucket
        description: canonical admin_dong_code 또는 __UNMAPPED__입니다.
        tests: [not_null]
      - name: admin_dong_code
        description: canonical bucket의 정본 코드이며 unmapped bucket에서는 null입니다.
      - name: admin_dong
        description: canonical 행정동명이며 unmapped bucket에서는 null입니다.
      - name: gu_code
        description: canonical 자치구 코드이며 unmapped bucket에서는 null입니다.
      - name: gu
        description: canonical 자치구명이며 unmapped bucket에서는 null입니다.
      - name: admin_dong_revision_date
        description: canonical stamp revision이며 unmapped bucket에서는 null입니다.
      - name: snapshot_dag_run_id
        description: current Silver가 상속한 pinned incident run입니다.
        tests: [not_null]
      - name: snapshot_run_count
        description: bucket 안 distinct pinned run 수이며 항상 1이어야 합니다.
        tests: [not_null]
      - name: evidence_scope
        description: pinned current snapshot을 occurrence day로 재집계했음을 나타냅니다.
        tests:
          - accepted_values:
              arguments:
                values: ['pinned_current_snapshot_by_occurrence_day']
      - name: incident_count
        description: expected_clear_at null 여부와 무관한 current incident 수입니다.
        tests: [not_null]
      - name: expected_clearance_present_count
        description: expected_clear_at이 있는 incident 수입니다.
        tests: [not_null]
      - name: expected_clearance_missing_count
        description: expected_clear_at이 없는 incident 수입니다.
        tests: [not_null]
      - name: expected_clearance_usable_count
        description: expected_clear_at이 occurred_at 이상인 incident 수입니다.
        tests: [not_null]
      - name: expected_clearance_invalid_count
        description: expected_clear_at이 occurred_at보다 이른 incident 수입니다.
        tests: [not_null]
      - name: expected_clearance_present_ratio
        description: present count를 incident_count로 나눈 비율입니다.
        tests: [not_null]
      - name: expected_clearance_missing_ratio
        description: missing count를 incident_count로 나눈 비율입니다.
        tests: [not_null]
      - name: expected_clearance_usable_ratio
        description: usable count를 incident_count로 나눈 비율입니다.
        tests: [not_null]
      - name: expected_clearance_invalid_ratio
        description: invalid count를 incident_count로 나눈 비율입니다.
        tests: [not_null]
      - name: min_expected_clearance_lead_minutes
        description: usable source expectation의 최소 lead minutes이며 실제 duration이 아닙니다.
      - name: avg_expected_clearance_lead_minutes
        description: usable source expectation의 평균 lead minutes이며 실제 duration이 아닙니다.
      - name: max_expected_clearance_lead_minutes
        description: usable source expectation의 최대 lead minutes이며 실제 duration이 아닙니다.
      - name: profile_state
        description: expected-clear evidence의 없음, invalid-only, partial, complete 상태입니다.
        tests:
          - not_null
          - accepted_values:
              arguments:
                values:
                  - no_expected_clearance_evidence
                  - invalid_expected_clearance_evidence
                  - partial_expected_clearance_evidence
                  - complete_expected_clearance_evidence
~~~

- [ ] **Step 6: Run compile-only GREEN with synthetic vars**

Run:

~~~bash
dbt --log-path /tmp/asac-dbt-traffic-quality-gold-logs compile --project-dir domains/traffic_weather --profiles-dir domains/traffic_weather --target dev --select gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily assert_gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily_grain_unique assert_gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily_reconciles --target-path /tmp/asac-dbt-traffic-quality-gold-compile-clearance --vars "$DBT_COMPILE_VARS"
~~~

Expected: PASS. This is compile-only evidence.

- [ ] **Step 7: Run dev runtime GREEN with the real pinned incident run**

Run:

~~~bash
dbt --log-path /tmp/asac-dbt-traffic-quality-gold-logs run --project-dir domains/traffic_weather --profiles-dir domains/traffic_weather --target dev --select silver_seoul_traffic_incident silver_seoul_traffic_incident_current gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily --target-path /tmp/asac-dbt-traffic-quality-gold-run-clearance --vars "$DBT_TRAFFIC_VARS"
dbt --log-path /tmp/asac-dbt-traffic-quality-gold-logs test --project-dir domains/traffic_weather --profiles-dir domains/traffic_weather --target dev --select assert_gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily_grain_unique assert_gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily_reconciles --target-path /tmp/asac-dbt-traffic-quality-gold-test-clearance --vars "$DBT_TRAFFIC_VARS"
~~~

Expected: selected Traffic models and both singular tests PASS. The existing common axes relations are read, not rebuilt.

- [ ] **Step 8: Confirm exact-five inventory remains RED for one missing product**

Run:

~~~bash
python3 -m pytest domains/traffic_weather/tests/traffic/test_traffic_quality_gold_contract.py::test_traffic_quality_gold_metadata_ship_set_is_exactly_five domains/traffic_weather/tests/traffic/test_traffic_quality_gold_contract.py::test_traffic_quality_gold_physical_ship_set_is_exactly_five -q
~~~

Expected: 2 failed because the spatial-quality model and metadata entry do not exist yet.

---

### Task 4: Add spatial mapping quality by occurrence day and mapping bucket

**Files:**
- Create: domains/traffic_weather/models/traffic/transform/gold/gold_traffic_incident_spatial_mapping_quality_daily.sql
- Modify: domains/traffic_weather/models/traffic/transform/gold/_gold.yml
- Create: domains/traffic_weather/tests/traffic/transform/gold/assert_gold_traffic_incident_spatial_mapping_quality_daily_grain_unique.sql
- Create: domains/traffic_weather/tests/traffic/transform/gold/assert_gold_traffic_incident_spatial_mapping_quality_daily_reconciles.sql

**Interfaces:**
- Consumes: pinned silver_seoul_traffic_incident_current coordinate and candidate admin fields plus canonical dim_admin_dong.
- Produces: quality_day × mapping_bucket rows. The __UNMAPPED__ row keeps admin_dong_code nullable and separates source-coordinate missing, WGS84 conversion/bbox miss, boundary miss, and canonical miss.

- [ ] **Step 1: Write the failing grain and mutually-exclusive category test**

Create domains/traffic_weather/tests/traffic/transform/gold/assert_gold_traffic_incident_spatial_mapping_quality_daily_grain_unique.sql with exactly:

~~~sql
-- depends_on: {{ ref('gold_traffic_incident_spatial_mapping_quality_daily') }}

{% set snapshot_dag_run_id = var('traffic_snapshot_dag_run_id') %}

with checked as (
    select
        *,
        count(*) over (
            partition by quality_day, mapping_bucket
        ) as natural_grain_row_count,
        count(*) over (
            partition by product_row_id
        ) as product_row_id_row_count
    from {{ ref('gold_traffic_incident_spatial_mapping_quality_daily') }}
)

select *
from checked
where product_row_id is null
   or quality_day is null
   or mapping_bucket is null
   or snapshot_dag_run_id is null
   or snapshot_dag_run_id is distinct from '{{ snapshot_dag_run_id | replace("'", "''") }}'
   or snapshot_run_count <> 1
   or evidence_scope is distinct from 'pinned_current_snapshot_by_occurrence_day'
   or natural_grain_row_count <> 1
   or product_row_id_row_count <> 1
   or product_row_id is distinct from concat(
       cast(quality_day as varchar),
       '|',
       mapping_bucket
   )
   or incident_count <= 0
   or mapped_incident_count < 0
   or source_coordinate_missing_count < 0
   or wgs84_conversion_or_bbox_miss_count < 0
   or boundary_match_missing_count < 0
   or canonical_admin_miss_count < 0
   or incident_count is distinct from (
       mapped_incident_count
       + source_coordinate_missing_count
       + wgs84_conversion_or_bbox_miss_count
       + boundary_match_missing_count
       + canonical_admin_miss_count
   )
   or abs(
       mapping_success_ratio
       - cast(mapped_incident_count as double) / cast(incident_count as double)
   ) > 0.000000000001
   or abs(
       source_coordinate_missing_ratio
       - cast(source_coordinate_missing_count as double)
         / cast(incident_count as double)
   ) > 0.000000000001
   or abs(
       wgs84_conversion_or_bbox_miss_ratio
       - cast(wgs84_conversion_or_bbox_miss_count as double)
         / cast(incident_count as double)
   ) > 0.000000000001
   or abs(
       boundary_match_missing_ratio
       - cast(boundary_match_missing_count as double)
         / cast(incident_count as double)
   ) > 0.000000000001
   or abs(
       canonical_admin_miss_ratio
       - cast(canonical_admin_miss_count as double)
         / cast(incident_count as double)
   ) > 0.000000000001
   or (
       mapping_bucket = '__UNMAPPED__'
       and (
           mapping_state is distinct from 'unmapped'
           or admin_dong_code is not null
           or admin_dong is not null
           or gu_code is not null
           or gu is not null
           or admin_dong_revision_date is not null
           or mapped_incident_count <> 0
       )
   )
   or (
       mapping_bucket <> '__UNMAPPED__'
       and (
           mapping_state is distinct from 'mapped'
           or admin_dong_code is distinct from mapping_bucket
           or admin_dong is null
           or gu_code is null
           or gu is null
           or admin_dong_revision_date is null
           or mapped_incident_count <> incident_count
           or source_coordinate_missing_count <> 0
           or wgs84_conversion_or_bbox_miss_count <> 0
           or boundary_match_missing_count <> 0
           or canonical_admin_miss_count <> 0
       )
   )
~~~

- [ ] **Step 2: Write the failing source reconciliation test**

Create domains/traffic_weather/tests/traffic/transform/gold/assert_gold_traffic_incident_spatial_mapping_quality_daily_reconciles.sql with exactly:

~~~sql
-- depends_on: {{ ref('gold_traffic_incident_spatial_mapping_quality_daily') }}
-- depends_on: {{ ref('silver_seoul_traffic_incident_current') }}
-- depends_on: {{ ref('asac_axes', 'dim_admin_dong') }}

with canonical_raw as (
    select
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(admin_dong as varchar) as admin_dong,
        cast(gu_code as varchar) as gu_code,
        cast(gu as varchar) as gu,
        try_cast(revision_date as date) as admin_dong_revision_date
    from {{ ref('asac_axes', 'dim_admin_dong') }}
),

canonical_ranked as (
    select
        *,
        row_number() over (
            partition by admin_dong_code
            order by
                admin_dong_revision_date desc nulls last,
                admin_dong asc nulls last,
                gu_code asc nulls last,
                gu asc nulls last
        ) as canonical_row_num
    from canonical_raw
),

canonical as (
    select *
    from canonical_ranked
    where admin_dong_code is not null
      and canonical_row_num = 1
),

classified as (
    select
        cast(current_snapshot.occurred_at as date) as quality_day,
        coalesce(canonical.admin_dong_code, '__UNMAPPED__') as mapping_bucket,
        canonical.admin_dong_code,
        canonical.admin_dong,
        canonical.gu_code,
        canonical.gu,
        canonical.admin_dong_revision_date,
        cast(current_snapshot.dag_run_id as varchar) as snapshot_dag_run_id,
        case
            when canonical.admin_dong_code is not null
                then 'mapped'
            when current_snapshot.source_location_quality
                    = 'source_coordinate_missing'
              or current_snapshot.grs80tm_x is null
              or current_snapshot.grs80tm_y is null
                then 'source_coordinate_missing'
            when current_snapshot.longitude is null
              or current_snapshot.latitude is null
                then 'wgs84_conversion_or_bbox_miss'
            when current_snapshot.admin_dong_code is null
                then 'boundary_match_missing'
            else 'canonical_admin_miss'
        end as mapping_evidence_class
    from {{ ref('silver_seoul_traffic_incident_current') }} as current_snapshot
    left join canonical
        on cast(current_snapshot.admin_dong_code as varchar)
            = canonical.admin_dong_code
    where current_snapshot.occurred_at is not null
),

evidence as (
    select
        quality_day,
        mapping_bucket,
        admin_dong_code,
        admin_dong,
        gu_code,
        gu,
        admin_dong_revision_date,
        max(snapshot_dag_run_id) as snapshot_dag_run_id,
        count(distinct snapshot_dag_run_id) as snapshot_run_count,
        count(*) as incident_count,
        count_if(mapping_evidence_class = 'mapped')
            as mapped_incident_count,
        count_if(mapping_evidence_class = 'source_coordinate_missing')
            as source_coordinate_missing_count,
        count_if(mapping_evidence_class = 'wgs84_conversion_or_bbox_miss')
            as wgs84_conversion_or_bbox_miss_count,
        count_if(mapping_evidence_class = 'boundary_match_missing')
            as boundary_match_missing_count,
        count_if(mapping_evidence_class = 'canonical_admin_miss')
            as canonical_admin_miss_count
    from classified
    group by
        quality_day,
        mapping_bucket,
        admin_dong_code,
        admin_dong,
        gu_code,
        gu,
        admin_dong_revision_date
),

expected as (
    select
        concat(cast(quality_day as varchar), '|', mapping_bucket)
            as product_row_id,
        quality_day,
        mapping_bucket,
        admin_dong_code,
        admin_dong,
        gu_code,
        gu,
        admin_dong_revision_date,
        snapshot_dag_run_id,
        snapshot_run_count,
        cast('pinned_current_snapshot_by_occurrence_day' as varchar)
            as evidence_scope,
        incident_count,
        mapped_incident_count,
        source_coordinate_missing_count,
        wgs84_conversion_or_bbox_miss_count,
        boundary_match_missing_count,
        canonical_admin_miss_count,
        cast(mapped_incident_count as double) / cast(incident_count as double)
            as mapping_success_ratio,
        cast(source_coordinate_missing_count as double)
            / cast(incident_count as double)
            as source_coordinate_missing_ratio,
        cast(wgs84_conversion_or_bbox_miss_count as double)
            / cast(incident_count as double)
            as wgs84_conversion_or_bbox_miss_ratio,
        cast(boundary_match_missing_count as double)
            / cast(incident_count as double)
            as boundary_match_missing_ratio,
        cast(canonical_admin_miss_count as double)
            / cast(incident_count as double)
            as canonical_admin_miss_ratio,
        case
            when mapping_bucket = '__UNMAPPED__' then 'unmapped'
            else 'mapped'
        end as mapping_state
    from evidence
),

actual as (
    select
        product_row_id,
        quality_day,
        mapping_bucket,
        admin_dong_code,
        admin_dong,
        gu_code,
        gu,
        admin_dong_revision_date,
        snapshot_dag_run_id,
        snapshot_run_count,
        evidence_scope,
        incident_count,
        mapped_incident_count,
        source_coordinate_missing_count,
        wgs84_conversion_or_bbox_miss_count,
        boundary_match_missing_count,
        canonical_admin_miss_count,
        mapping_success_ratio,
        source_coordinate_missing_ratio,
        wgs84_conversion_or_bbox_miss_ratio,
        boundary_match_missing_ratio,
        canonical_admin_miss_ratio,
        mapping_state
    from {{ ref('gold_traffic_incident_spatial_mapping_quality_daily') }}
),

missing_rows as (
    select * from expected
    except
    select * from actual
),

extra_rows as (
    select * from actual
    except
    select * from expected
)

select 'missing_expected_row' as violation_type, *
from missing_rows

union all

select 'extra_actual_row' as violation_type, *
from extra_rows
~~~

- [ ] **Step 3: Run the RED parse**

Run:

~~~bash
dbt --log-path /tmp/asac-dbt-traffic-quality-gold-logs parse --project-dir domains/traffic_weather --profiles-dir domains/traffic_weather --target dev --no-partial-parse --target-path /tmp/asac-dbt-traffic-quality-gold-red-spatial --vars "$DBT_COMPILE_VARS"
~~~

Expected: FAIL because both singular tests ref the absent spatial-quality model.

- [ ] **Step 4: Implement the complete spatial-quality model**

Create domains/traffic_weather/models/traffic/transform/gold/gold_traffic_incident_spatial_mapping_quality_daily.sql with exactly:

~~~sql
-- Spatial mapping evidence among incidents present in the pinned current snapshot.
-- Unmapped rows keep canonical admin fields null and retain a reason category.
-- depends_on: {{ ref('silver_seoul_traffic_incident_current') }}
-- depends_on: {{ ref('asac_axes', 'dim_admin_dong') }}

{{ config(materialized='table') }}

with canonical_raw as (
    select
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(admin_dong as varchar) as admin_dong,
        cast(gu_code as varchar) as gu_code,
        cast(gu as varchar) as gu,
        try_cast(revision_date as date) as admin_dong_revision_date
    from {{ ref('asac_axes', 'dim_admin_dong') }}
),

canonical_ranked as (
    select
        *,
        row_number() over (
            partition by admin_dong_code
            order by
                admin_dong_revision_date desc nulls last,
                admin_dong asc nulls last,
                gu_code asc nulls last,
                gu asc nulls last
        ) as canonical_row_num
    from canonical_raw
),

canonical as (
    select *
    from canonical_ranked
    where admin_dong_code is not null
      and canonical_row_num = 1
),

classified as (
    select
        cast(current_snapshot.occurred_at as date) as quality_day,
        coalesce(canonical.admin_dong_code, '__UNMAPPED__') as mapping_bucket,
        canonical.admin_dong_code,
        canonical.admin_dong,
        canonical.gu_code,
        canonical.gu,
        canonical.admin_dong_revision_date,
        cast(current_snapshot.dag_run_id as varchar) as snapshot_dag_run_id,
        case
            when canonical.admin_dong_code is not null
                then 'mapped'
            when current_snapshot.source_location_quality
                    = 'source_coordinate_missing'
              or current_snapshot.grs80tm_x is null
              or current_snapshot.grs80tm_y is null
                then 'source_coordinate_missing'
            when current_snapshot.longitude is null
              or current_snapshot.latitude is null
                then 'wgs84_conversion_or_bbox_miss'
            when current_snapshot.admin_dong_code is null
                then 'boundary_match_missing'
            else 'canonical_admin_miss'
        end as mapping_evidence_class
    from {{ ref('silver_seoul_traffic_incident_current') }} as current_snapshot
    left join canonical
        on cast(current_snapshot.admin_dong_code as varchar)
            = canonical.admin_dong_code
    where current_snapshot.occurred_at is not null
),

quality_evidence as (
    select
        quality_day,
        mapping_bucket,
        admin_dong_code,
        admin_dong,
        gu_code,
        gu,
        admin_dong_revision_date,
        max(snapshot_dag_run_id) as snapshot_dag_run_id,
        count(distinct snapshot_dag_run_id) as snapshot_run_count,
        count(*) as incident_count,
        count_if(mapping_evidence_class = 'mapped')
            as mapped_incident_count,
        count_if(mapping_evidence_class = 'source_coordinate_missing')
            as source_coordinate_missing_count,
        count_if(mapping_evidence_class = 'wgs84_conversion_or_bbox_miss')
            as wgs84_conversion_or_bbox_miss_count,
        count_if(mapping_evidence_class = 'boundary_match_missing')
            as boundary_match_missing_count,
        count_if(mapping_evidence_class = 'canonical_admin_miss')
            as canonical_admin_miss_count
    from classified
    group by
        quality_day,
        mapping_bucket,
        admin_dong_code,
        admin_dong,
        gu_code,
        gu,
        admin_dong_revision_date
)

select
    concat(cast(quality_day as varchar), '|', mapping_bucket)
        as product_row_id,
    quality_day,
    mapping_bucket,
    admin_dong_code,
    admin_dong,
    gu_code,
    gu,
    admin_dong_revision_date,
    snapshot_dag_run_id,
    snapshot_run_count,
    cast('pinned_current_snapshot_by_occurrence_day' as varchar)
        as evidence_scope,
    incident_count,
    mapped_incident_count,
    source_coordinate_missing_count,
    wgs84_conversion_or_bbox_miss_count,
    boundary_match_missing_count,
    canonical_admin_miss_count,
    cast(mapped_incident_count as double) / cast(incident_count as double)
        as mapping_success_ratio,
    cast(source_coordinate_missing_count as double)
        / cast(incident_count as double)
        as source_coordinate_missing_ratio,
    cast(wgs84_conversion_or_bbox_miss_count as double)
        / cast(incident_count as double)
        as wgs84_conversion_or_bbox_miss_ratio,
    cast(boundary_match_missing_count as double)
        / cast(incident_count as double)
        as boundary_match_missing_ratio,
    cast(canonical_admin_miss_count as double)
        / cast(incident_count as double)
        as canonical_admin_miss_ratio,
    case
        when mapping_bucket = '__UNMAPPED__' then 'unmapped'
        else 'mapped'
    end as mapping_state
from quality_evidence
~~~

- [ ] **Step 5: Add the complete spatial-quality YAML entry**

Append this model entry to domains/traffic_weather/models/traffic/transform/gold/_gold.yml:

~~~yaml
  - name: gold_traffic_incident_spatial_mapping_quality_daily
    description: 고정 current snapshot의 incident를 발생일과 canonical 또는 unmapped bucket으로 묶고 공간 매핑 실패 원인을 상호배타적으로 분리하는 제품입니다.
    config:
      meta:
        traffic_quality_product: true
    columns:
      - name: product_row_id
        description: quality_day와 mapping_bucket의 결정적 식별자입니다.
        tests: [not_null, unique]
      - name: quality_day
        description: occurred_at의 KST calendar date입니다.
        tests: [not_null]
      - name: mapping_bucket
        description: canonical admin_dong_code 또는 __UNMAPPED__입니다.
        tests: [not_null]
      - name: admin_dong_code
        description: canonical bucket의 정본 코드이며 unmapped bucket에서는 null입니다.
      - name: admin_dong
        description: canonical 행정동명이며 unmapped bucket에서는 null입니다.
      - name: gu_code
        description: canonical 자치구 코드이며 unmapped bucket에서는 null입니다.
      - name: gu
        description: canonical 자치구명이며 unmapped bucket에서는 null입니다.
      - name: admin_dong_revision_date
        description: canonical stamp revision이며 unmapped bucket에서는 null입니다.
      - name: snapshot_dag_run_id
        description: current Silver가 상속한 pinned incident run입니다.
        tests: [not_null]
      - name: snapshot_run_count
        description: bucket 안 distinct pinned run 수이며 항상 1이어야 합니다.
        tests: [not_null]
      - name: evidence_scope
        description: pinned current snapshot을 occurrence day로 재집계했음을 나타냅니다.
        tests:
          - accepted_values:
              arguments:
                values: ['pinned_current_snapshot_by_occurrence_day']
      - name: incident_count
        description: bucket의 current incident 수입니다.
        tests: [not_null]
      - name: mapped_incident_count
        description: canonical dimension에 exact join된 incident 수입니다.
        tests: [not_null]
      - name: source_coordinate_missing_count
        description: source GRS80 TM coordinate pair가 없는 incident 수입니다.
        tests: [not_null]
      - name: wgs84_conversion_or_bbox_miss_count
        description: source coordinate는 있으나 WGS84 변환 또는 Seoul bbox guard 후 좌표가 없는 incident 수입니다.
        tests: [not_null]
      - name: boundary_match_missing_count
        description: WGS84 좌표는 있으나 Silver boundary match code가 없는 incident 수입니다.
        tests: [not_null]
      - name: canonical_admin_miss_count
        description: Silver candidate admin code는 있으나 canonical dimension에 없는 incident 수입니다.
        tests: [not_null]
      - name: mapping_success_ratio
        description: mapped incident를 incident_count로 나눈 비율입니다.
        tests: [not_null]
      - name: source_coordinate_missing_ratio
        description: source-coordinate-missing count를 incident_count로 나눈 비율입니다.
        tests: [not_null]
      - name: wgs84_conversion_or_bbox_miss_ratio
        description: conversion/bbox miss count를 incident_count로 나눈 비율입니다.
        tests: [not_null]
      - name: boundary_match_missing_ratio
        description: boundary miss count를 incident_count로 나눈 비율입니다.
        tests: [not_null]
      - name: canonical_admin_miss_ratio
        description: canonical miss count를 incident_count로 나눈 비율입니다.
        tests: [not_null]
      - name: mapping_state
        description: mapping_bucket이 canonical이면 mapped, __UNMAPPED__이면 unmapped입니다.
        tests:
          - not_null
          - accepted_values:
              arguments:
                values: ['mapped', 'unmapped']
~~~

- [ ] **Step 6: Run compile-only GREEN with synthetic vars**

Run:

~~~bash
dbt --log-path /tmp/asac-dbt-traffic-quality-gold-logs compile --project-dir domains/traffic_weather --profiles-dir domains/traffic_weather --target dev --select gold_traffic_incident_spatial_mapping_quality_daily assert_gold_traffic_incident_spatial_mapping_quality_daily_grain_unique assert_gold_traffic_incident_spatial_mapping_quality_daily_reconciles --target-path /tmp/asac-dbt-traffic-quality-gold-compile-spatial --vars "$DBT_COMPILE_VARS"
~~~

Expected: PASS. This is compile-only evidence.

- [ ] **Step 7: Run dev runtime GREEN with the real pinned incident run**

Run:

~~~bash
dbt --log-path /tmp/asac-dbt-traffic-quality-gold-logs run --project-dir domains/traffic_weather --profiles-dir domains/traffic_weather --target dev --select silver_seoul_traffic_incident silver_seoul_traffic_incident_current gold_traffic_incident_spatial_mapping_quality_daily --target-path /tmp/asac-dbt-traffic-quality-gold-run-spatial --vars "$DBT_TRAFFIC_VARS"
dbt --log-path /tmp/asac-dbt-traffic-quality-gold-logs test --project-dir domains/traffic_weather --profiles-dir domains/traffic_weather --target dev --select assert_gold_traffic_incident_spatial_mapping_quality_daily_grain_unique assert_gold_traffic_incident_spatial_mapping_quality_daily_reconciles --target-path /tmp/asac-dbt-traffic-quality-gold-test-spatial --vars "$DBT_TRAFFIC_VARS"
~~~

Expected: selected Traffic models and both singular tests PASS.

- [ ] **Step 8: Turn exact-five metadata and physical inventory GREEN**

Run:

~~~bash
python3 -m pytest domains/traffic_weather/tests/traffic/test_traffic_quality_gold_contract.py -q
~~~

Expected: 3 passed. This is the first point where the plan requires the physical inventory test to be GREEN.

---

### Task 5: Document the five products and run integrated verification

**Files:**
- Modify: domains/traffic_weather/models/traffic/README.md
- Modify: domains/traffic_weather/docs/traffic/dbt_contracts.md
- Verify: domains/traffic_weather/models/traffic/transform/gold/_gold.yml
- Verify: domains/traffic_weather/models/traffic/transform/gold/gold_traffic_incident_current_by_admin_dong_hourly.yml
- Verify: domains/traffic_weather/tests/traffic/test_traffic_quality_gold_contract.py

**Interfaces:**
- Consumes: the five-product metadata/physical inventory and all six new singular tests.
- Produces: exact user-facing scope, isolated dev dbt evidence, pytest evidence, and a clean scoped diff without Gate B actions.

- [ ] **Step 1: Add the exact README product section**

Add this section to domains/traffic_weather/models/traffic/README.md:

~~~markdown
## Traffic Quality Gold ship set

승인된 Traffic Quality Gold 제품은 정확히 다음 5개다.

1. gold_traffic_incident_current_by_admin_dong_hourly
2. gold_traffic_incident_x_flow
3. gold_traffic_incident_collection_coverage_5m
4. gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily
5. gold_traffic_incident_spatial_mapping_quality_daily

gold_traffic_incident_summary는 support-only relation이며 위 ship set에 포함하지 않는다.

collection coverage는 evidence_scope=materialized_snapshot_only인 request-audit 관측 제품이다. 실제 audit row가 있는 수집 5분 구간만 표현하며, landing하지 않은 schedule slot이나 Airflow missed run을 생성하거나 추론하지 않는다.

expected-clearance profile과 spatial mapping quality는 traffic_snapshot_dag_run_id로 고정된 current Silver를 occurred_at의 KST date로 재집계한다. 두 모델의 mapping_bucket은 canonical admin_dong_code 또는 __UNMAPPED__이며 unmapped row의 canonical stamp는 null이다.
~~~

- [ ] **Step 2: Add the exact dbt contract section**

Add this section to domains/traffic_weather/docs/traffic/dbt_contracts.md:

~~~markdown
## Traffic Quality Gold five-product contract

Traffic Quality Gold 승인 ship set은 current-by-admin-hour, incident-x-flow, materialized request-audit coverage, expected-clearance evidence profile, spatial mapping quality의 5개 제품으로 고정한다. gold_traffic_incident_summary는 current snapshot 검증과 소규모 집계를 지원하는 support-only relation이다.

gold_traffic_incident_collection_coverage_5m의 grain은 source_id × coverage_window_at_utc다. coverage_window_at_utc는 실제 request-audit collected_at을 UTC-naive 5분 경계로 내린 값이며 evidence_scope는 materialized_snapshot_only다. source/run별 latest effective manifest state를 먼저 선택한 뒤 상태를 판정한다. audit가 없는 5분 구간, 미착륙 schedule slot, Airflow missed run은 row로 만들지 않으므로 이 모델은 scheduled collection SLO가 아니다.

gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily의 grain은 profile_day × mapping_bucket이다. profile_day는 pinned current incident의 occurred_at KST date다. expected_clear_at이 null인 incident도 incident_count와 missing ratio에 포함한다. expected_clearance_lead_minutes는 expected_clear_at과 occurred_at의 source-provided 예상 간격이며 실제 해결시간이 아니다.

gold_traffic_incident_spatial_mapping_quality_daily의 grain은 quality_day × mapping_bucket이다. mapping_bucket은 canonical admin_dong_code 또는 __UNMAPPED__이다. unmapped row의 admin_dong_code와 canonical stamp는 null이며 source-coordinate missing, WGS84 conversion/bbox miss, boundary match miss, canonical dimension miss를 별도 count로 제공한다.
~~~

- [ ] **Step 3: Install dependencies outside the worktree and run fresh parse/compile**

Run:

~~~bash
dbt --log-path /tmp/asac-dbt-traffic-quality-gold-logs deps --project-dir domains/traffic_weather --profiles-dir domains/traffic_weather
dbt --log-path /tmp/asac-dbt-traffic-quality-gold-logs parse --project-dir domains/traffic_weather --profiles-dir domains/traffic_weather --target dev --no-partial-parse --target-path /tmp/asac-dbt-traffic-quality-gold-final-parse --vars "$DBT_COMPILE_VARS"
dbt --log-path /tmp/asac-dbt-traffic-quality-gold-logs compile --project-dir domains/traffic_weather --profiles-dir domains/traffic_weather --target dev --select gold_traffic_incident_current_by_admin_dong_hourly gold_traffic_incident_x_flow gold_traffic_incident_collection_coverage_5m gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily gold_traffic_incident_spatial_mapping_quality_daily gold_traffic_incident_summary path:tests/traffic/transform/gold --target-path /tmp/asac-dbt-traffic-quality-gold-final-compile --vars "$DBT_COMPILE_VARS"
~~~

Expected: dependency install, fresh parse, and selected compile PASS. Synthetic vars are used only in parse/compile.

- [ ] **Step 4: Run the integrated Traffic-only dev graph with actual latest-run vars**

Run:

~~~bash
dbt --log-path /tmp/asac-dbt-traffic-quality-gold-logs run --project-dir domains/traffic_weather --profiles-dir domains/traffic_weather --target dev --select silver_seoul_traffic_incident silver_seoul_traffic_incident_current silver_seoul_traffic_flow gold_traffic_incident_current_by_admin_dong_hourly gold_traffic_incident_x_flow gold_traffic_incident_collection_coverage_5m gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily gold_traffic_incident_spatial_mapping_quality_daily gold_traffic_incident_summary --target-path /tmp/asac-dbt-traffic-quality-gold-final-run --vars "$DBT_TRAFFIC_VARS"
dbt --log-path /tmp/asac-dbt-traffic-quality-gold-logs test --project-dir domains/traffic_weather --profiles-dir domains/traffic_weather --target dev --select path:models/traffic/transform/gold path:tests/traffic/transform/gold --target-path /tmp/asac-dbt-traffic-quality-gold-final-test --vars "$DBT_TRAFFIC_VARS"
~~~

Expected: all selected Traffic models and Gold tests PASS. Only the isolated TRAFFIC_SCHEMA is written; common axes relations are read-only.

- [ ] **Step 5: Run repository contract tests**

Run:

~~~bash
python3 -m pytest domains/traffic_weather/tests/traffic/test_traffic_quality_gold_contract.py domains/traffic_weather/tests/traffic/test_canonical_gold_contract.py domains/traffic_weather/tests/traffic/test_current_state_contract.py -q
~~~

Expected: all selected pytest tests PASS.

- [ ] **Step 6: Run final scope and whitespace verification**

Run:

~~~bash
git diff --check
git status --short
git diff -- domains/traffic_weather/models/traffic domains/traffic_weather/tests/traffic domains/traffic_weather/docs/traffic
~~~

Expected: git diff --check exits 0; status shows only approved Traffic model/test/doc paths; the diff contains no common, weather, package, DAG, profile, selector, project-root, commit, push, or merge change.

- [ ] **Step 7: Stop before Gate B**

Report PASS/FAIL/NOT RUN for pytest, dbt deps/parse/compile/run/test, exact-five inventory, and git diff --check. Do not stage, commit, push, create a PR, or merge.
