-- Canonical Traffic current-state mart.
--
-- Grain: one row per canonical admin_dong_code and snapshot evaluation hour.
-- The transform DAG pins traffic_snapshot_dag_run_id once; this model never
-- re-anchors to a newer live run while the invocation is in progress.
-- Names, district fields, and revision are stamped only from dim_admin_dong.
-- GRS80 TM coordinates are deliberately not interpreted in Gold.
-- depends_on: {{ ref('silver_seoul_traffic_incident_current') }}
-- depends_on: {{ ref('asac_axes', 'seoul_admin_dong_crosswalk') }}
-- depends_on: {{ source('axes_bronze', 'admin_dong_master') }}

{{ config(materialized='table') }}

{% set snapshot_dag_run_id = var('traffic_snapshot_dag_run_id') %}
{% set published_at_utc = run_started_at.strftime('%Y-%m-%d %H:%M:%S.%f') %}

with configured_run as (
    select
        cast('{{ snapshot_dag_run_id | replace("'", "''") }}' as varchar) as snapshot_dag_run_id,
        cast('seoul_traffic_incident' as varchar) as source_id,
        cast(timestamp '{{ published_at_utc }}' + interval '9' hour as timestamp(6)) as published_at
),

latest_manifest_state as (
    {{ latest_manifest_run_state('traffic_bronze', 'collection_run_manifest', 'seoul_traffic_incident') }}
),

manifest_candidates as (
    select
        manifest.dag_run_id as manifest_dag_run_id,
        manifest.manifest_status,
        manifest.is_publishable,
        manifest.manifest_event_at_utc,
        try_cast(manifest.manifest_expected_rows as integer) as expected_rows,
        try_cast(manifest.manifest_actual_rows as integer) as actual_rows,
        try_cast(manifest.manifest_expected_raw_objects as integer) as expected_raw_objects,
        try_cast(manifest.manifest_actual_raw_objects as integer) as actual_raw_objects,
        manifest.manifest_failure_reason as failure_reason,
        manifest.manifest_state_tie_count as manifest_latest_tie_count
    from latest_manifest_state as manifest
    cross join configured_run
    where manifest.dag_run_id = configured_run.snapshot_dag_run_id
),

manifest_evidence as (
    select
        configured_run.snapshot_dag_run_id,
        configured_run.source_id,
        configured_run.published_at,
        manifest_candidates.manifest_dag_run_id,
        manifest_candidates.manifest_status,
        manifest_candidates.is_publishable,
        manifest_candidates.manifest_event_at_utc,
        cast(
            {{ asac_axes.utc_to_kst('manifest_candidates.manifest_event_at_utc') }}
            as timestamp(6)
        ) as manifest_event_at_kst,
        manifest_candidates.expected_rows,
        manifest_candidates.actual_rows,
        manifest_candidates.expected_raw_objects,
        manifest_candidates.actual_raw_objects,
        manifest_candidates.failure_reason,
        coalesce(manifest_candidates.manifest_latest_tie_count, cast(0 as bigint))
            as manifest_latest_tie_count
    from configured_run
    left join manifest_candidates
        on true
),

audit_rows as (
    select
        cast(audit.request_id as varchar) as request_id,
        cast(audit.source_id as varchar) as source_id,
        cast(audit.request_params_json as varchar) as request_params_json,
        try_cast(audit.start_index as integer) as start_index,
        try_cast(audit.end_index as integer) as end_index,
        cast(audit.raw_object_key as varchar) as raw_object_key,
        cast(audit.payload_hash as varchar) as payload_hash,
        try_cast(audit.http_status as integer) as http_status,
        cast(audit.result_code as varchar) as result_code,
        cast(audit.result_msg as varchar) as result_msg,
        try_cast(audit.list_total_count as integer) as list_total_count,
        try_cast(audit.row_count as integer) as row_count,
        cast(audit.collected_at as timestamp(6)) as collected_at,
        cast(audit.load_date as varchar) as load_date,
        cast(audit.dag_run_id as varchar) as dag_run_id
    from {{ source('traffic_bronze', 'seoul_traffic_incident_request_audit') }} as audit
    cross join configured_run
    where cast(audit.dag_run_id as varchar) = configured_run.snapshot_dag_run_id
),

audit_evidence as (
    select
        count(*) as audit_request_count,
        count_if(
            (http_status is not null and not (http_status between 200 and 299))
            or (result_code is not null and result_code <> 'INFO-000')
        ) as audit_api_failure_count,
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
        ) as audit_invalid_required_count,
        count_if(source_id is distinct from 'seoul_traffic_incident') as audit_wrong_source_count,
        count(distinct request_id) as audit_distinct_request_count,
        coalesce(sum(cast(row_count as bigint)), cast(0 as bigint)) as audited_row_count,
        max(list_total_count) as reported_total_count,
        count(distinct list_total_count) as reported_total_value_count,
        max(end_index) as max_page_end_index,
        cast(
            {{ asac_axes.utc_to_kst('max(collected_at)') }}
            as timestamp(6)
        ) as audit_snapshot_as_of_at,
        count(distinct raw_object_key) as audit_distinct_raw_object_count,
        count(*) - count(
            distinct concat(cast(start_index as varchar), '|', cast(end_index as varchar))
        ) as audit_duplicate_page_count
    from audit_rows
),

bronze_rows as (
    select
        cast(bronze.source_id as varchar) as source_id,
        cast(bronze.acc_id as varchar) as source_record_id,
        cast(bronze.result_code as varchar) as result_code,
        cast(bronze.raw_object_key as varchar) as raw_object_key,
        cast(bronze.occr_date as varchar) as occr_date,
        cast(bronze.occr_time as varchar) as occr_time,
        {{ asac_axes.kst_at_from_parts(
            'cast(bronze.occr_date as varchar)',
            'cast(bronze.occr_time as varchar)'
        ) }} as occurred_at
    from {{ source('traffic_bronze', 'seoul_traffic_incident') }} as bronze
    cross join configured_run
    where cast(bronze.dag_run_id as varchar) = configured_run.snapshot_dag_run_id
),

expected_current_ids as (
    select distinct source_record_id
    from bronze_rows
    where source_id = 'seoul_traffic_incident'
      and result_code = 'INFO-000'
      and source_record_id is not null
      and occurred_at is not null
),

bronze_evidence as (
    select
        count(*) as bronze_physical_row_count,
        count(distinct raw_object_key) as bronze_distinct_raw_object_count,
        count_if(source_id is distinct from 'seoul_traffic_incident') as bronze_wrong_source_count,
        count_if(result_code is distinct from 'INFO-000') as bronze_non_success_row_count,
        count_if(
            source_id = 'seoul_traffic_incident'
            and result_code = 'INFO-000'
            and (
                source_record_id is null
                or occurred_at is null
                or raw_object_key is null
            )
        ) as bronze_invalid_eligible_count,
        count_if(
            source_id = 'seoul_traffic_incident'
            and result_code = 'INFO-000'
            and source_record_id is not null
            and occurred_at is not null
        ) - count(
            distinct case
                when source_id = 'seoul_traffic_incident'
                 and result_code = 'INFO-000'
                 and source_record_id is not null
                 and occurred_at is not null
                    then source_record_id
            end
        ) as bronze_duplicate_valid_id_count,
        count(
            distinct case
                when source_id = 'seoul_traffic_incident'
                 and result_code = 'INFO-000'
                 and source_record_id is not null
                 and occurred_at is not null
                    then source_record_id
            end
        ) as valid_bronze_incident_count
    from bronze_rows
),

current_rows as (
    select
        cast(current_snapshot.source_record_id as varchar) as source_record_id,
        cast(current_snapshot.source_id as varchar) as source_id,
        cast(current_snapshot.admin_dong_code as varchar) as admin_dong_code,
        cast(current_snapshot.dag_run_id as varchar) as dag_run_id
    from {{ ref('silver_seoul_traffic_incident_current') }} as current_snapshot
),

current_ranked as (
    select
        *,
        row_number() over (
            partition by source_record_id
            order by dag_run_id desc nulls last, admin_dong_code asc nulls last
        ) as current_row_num
    from current_rows
),

actual_current_ids as (
    select distinct source_record_id
    from current_rows
    where source_record_id is not null
),

deduped_current as (
    select source_record_id, source_id, admin_dong_code, dag_run_id
    from current_ranked
    where source_record_id is not null
      and current_row_num = 1
),

current_evidence as (
    select
        count(*) as current_row_count,
        count_if(source_record_id is null) as current_null_id_count,
        count_if(source_record_id is not null) - count(distinct source_record_id)
            as current_duplicate_id_count,
        count_if(
            dag_run_id is distinct from (
                select snapshot_dag_run_id from configured_run
            )
        )
            as current_wrong_run_count,
        count_if(
            source_id is distinct from (
                select source_id from configured_run
            )
        )
            as current_wrong_source_count
    from current_rows
),

missing_current_ids as (
    select source_record_id from expected_current_ids
    except
    select source_record_id from actual_current_ids
),

extra_current_ids as (
    select source_record_id from actual_current_ids
    except
    select source_record_id from expected_current_ids
),

current_reconciliation as (
    select
        (select count(*) from missing_current_ids) as missing_current_count,
        (select count(*) from extra_current_ids) as extra_current_count
),

canonical_raw as (
    select
        cast(canonical.admin_dong_code as varchar) as admin_dong_code,
        cast(canonical.admin_dong as varchar) as admin_dong,
        cast(canonical.gu_code as varchar) as gu_code,
        cast(canonical.gu as varchar) as gu,
        try_cast(canonical.revision_date as date) as admin_dong_revision_date
    from {{ asac_axes.pinned_dim_admin_dong() }} as canonical
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

canonical_scaffold as (
    select
        admin_dong_code,
        admin_dong,
        gu_code,
        gu,
        admin_dong_revision_date
    from canonical_ranked
    where admin_dong_code is not null
      and canonical_row_num = 1
),

canonical_evidence as (
    select
        count(*) as canonical_row_count,
        count_if(admin_dong_code is null) as canonical_null_code_count,
        count_if(admin_dong_code is not null) - count(distinct admin_dong_code)
            as canonical_duplicate_code_count,
        count_if(
            admin_dong_code is null
            or admin_dong is null
            or gu_code is null
            or gu is null
            or admin_dong_revision_date is null
        ) as canonical_null_stamp_count
    from canonical_raw
),

mapped_current as (
    select
        current_snapshot.source_record_id,
        current_snapshot.admin_dong_code as candidate_admin_dong_code,
        canonical.admin_dong_code as canonical_admin_dong_code
    from deduped_current as current_snapshot
    left join canonical_scaffold as canonical
        on current_snapshot.admin_dong_code = canonical.admin_dong_code
),

mapped_counts as (
    select
        canonical_admin_dong_code as admin_dong_code,
        count(*) as mapped_incident_count
    from mapped_current
    where canonical_admin_dong_code is not null
    group by canonical_admin_dong_code
),

spatial_evidence as (
    select count_if(canonical_admin_dong_code is null) as unmapped_incident_count
    from mapped_current
),

snapshot_evidence as (
    select
        manifest_evidence.*,
        audit_evidence.*,
        bronze_evidence.*,
        current_evidence.*,
        current_reconciliation.*,
        canonical_evidence.*,
        spatial_evidence.*
    from manifest_evidence
    cross join audit_evidence
    cross join bronze_evidence
    cross join current_evidence
    cross join current_reconciliation
    cross join canonical_evidence
    cross join spatial_evidence
),

snapshot_state as (
    select
        *,
        case
            when manifest_dag_run_id is null
                then 'missing'
            when manifest_latest_tie_count > 1
                then 'partial'
            when audit_api_failure_count > 0
              or regexp_like(
                    coalesce(failure_reason, ''),
                    '^(HttpProblemError|ParseError) in land_seoul_traffic_raw$'
                 )
                then 'api_failure'
            when manifest_status = 'FAILED'
              or nullif(trim(coalesce(failure_reason, '')), '') is not null
                then 'partial'
            when audit_request_count = 0
                then 'missing'
            when manifest_event_at_utc is null
              or manifest_status is distinct from 'SUCCESS'
              or not coalesce(is_publishable, false)
              or expected_rows is null
              or actual_rows is null
              or expected_raw_objects is null
              or actual_raw_objects is null
              or expected_rows < 0
              or actual_rows < 0
              or expected_raw_objects <= 0
              or actual_raw_objects <= 0
              or expected_rows is distinct from actual_rows
              or expected_raw_objects is distinct from actual_raw_objects
              or audit_invalid_required_count > 0
              or audit_wrong_source_count > 0
              or reported_total_value_count <> 1
              or reported_total_count is distinct from expected_rows
              or audited_row_count is distinct from cast(expected_rows as bigint)
              or audit_request_count is distinct from cast(expected_raw_objects as bigint)
              or audit_distinct_request_count is distinct from audit_request_count
              or audit_distinct_raw_object_count is distinct from cast(actual_raw_objects as bigint)
              or audit_duplicate_page_count > 0
              or (expected_rows > 0 and max_page_end_index < expected_rows)
              or bronze_physical_row_count is distinct from cast(actual_rows as bigint)
              or bronze_wrong_source_count > 0
              or bronze_non_success_row_count > 0
              or bronze_invalid_eligible_count > 0
              or bronze_duplicate_valid_id_count > 0
              or valid_bronze_incident_count is distinct from cast(expected_rows as bigint)
              or (
                  expected_rows > 0
                  and bronze_distinct_raw_object_count
                      is distinct from cast(expected_raw_objects as bigint)
              )
                then 'partial'
            when current_null_id_count > 0
              or current_duplicate_id_count > 0
              or current_wrong_run_count > 0
              or current_wrong_source_count > 0
              or missing_current_count > 0
              or extra_current_count > 0
                then 'current_mismatch'
            when canonical_row_count = 0
              or canonical_null_code_count > 0
              or canonical_duplicate_code_count > 0
              or canonical_null_stamp_count > 0
              or unmapped_incident_count > 0
                then 'spatial_mapping_incomplete'
            when expected_rows = 0
                then 'complete_zero'
            else 'complete'
        end as quality_state
    from snapshot_evidence
),

state_times as (
    select
        *,
        cast(coalesce(manifest_event_at_kst, published_at) as timestamp(6)) as status_observed_at,
        cast(
            date_trunc('hour', coalesce(manifest_event_at_kst, published_at))
            as timestamp(6)
        ) as hour_at
    from snapshot_state
),

published_cells as (
    select
        canonical.admin_dong_code,
        canonical.admin_dong,
        canonical.gu_code,
        canonical.gu,
        canonical.admin_dong_revision_date,
        state.hour_at,
        state.quality_state,
        case
            when state.quality_state in ('complete', 'complete_zero')
                then cast(coalesce(mapped_counts.mapped_incident_count, 0) as bigint)
            else cast(null as bigint)
        end as incident_count,
        case
            when state.quality_state in ('complete', 'complete_zero')
                then coalesce(mapped_counts.mapped_incident_count, 0) > 0
            else cast(null as boolean)
        end as has_incident,
        case
            when state.quality_state in ('complete', 'complete_zero')
                then cast(state.audit_snapshot_as_of_at as timestamp(6))
            else cast(null as timestamp(6))
        end as snapshot_as_of_at,
        state.status_observed_at,
        state.published_at,
        state.snapshot_dag_run_id,
        state.source_id,
        cast(state.expected_rows as bigint) as expected_incident_count,
        cast(coalesce(state.audited_row_count, 0) as bigint) as audited_row_count,
        cast(state.max_page_end_index as integer) as max_page_end_index,
        cast(coalesce(state.unmapped_incident_count, 0) as bigint) as unmapped_incident_count
    from canonical_scaffold as canonical
    cross join state_times as state
    left join mapped_counts
        on canonical.admin_dong_code = mapped_counts.admin_dong_code
)

select
    concat(
        admin_dong_code,
        '|',
        to_iso8601(cast(hour_at as timestamp(6)))
    ) as product_row_id,
    admin_dong_code,
    hour_at,
    admin_dong,
    gu_code,
    gu,
    admin_dong_revision_date,
    incident_count,
    has_incident,
    quality_state,
    snapshot_as_of_at,
    status_observed_at,
    published_at,
    snapshot_dag_run_id,
    source_id,
    expected_incident_count,
    audited_row_count,
    max_page_end_index,
    unmapped_incident_count
from published_cells
