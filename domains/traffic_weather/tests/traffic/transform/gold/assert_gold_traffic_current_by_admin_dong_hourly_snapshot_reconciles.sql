{{ config(tags=['traffic_gold_gate']) }}
-- depends_on: {{ ref('silver_seoul_traffic_incident_current') }}
-- depends_on: {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}
-- depends_on: {{ ref('asac_axes', 'seoul_admin_dong_crosswalk') }}
-- depends_on: {{ source('axes_bronze', 'admin_dong_master') }}

{% set snapshot_dag_run_id = var('traffic_snapshot_dag_run_id') %}

with configured_run as (
    select
        '{{ snapshot_dag_run_id | replace("'", "''") }}' as dag_run_id,
        'seoul_traffic_incident' as source_id
),

latest_manifest_state as (
    {{ latest_manifest_run_state('traffic_bronze', 'collection_run_manifest', 'seoul_traffic_incident') }}
),

manifest_events as (
    select
        manifest.dag_run_id,
        manifest.manifest_status as status,
        manifest.is_publishable,
        manifest.manifest_event_at_utc as event_at,
        try_cast(manifest.manifest_expected_rows as integer) as expected_rows,
        try_cast(manifest.manifest_actual_rows as integer) as actual_rows,
        try_cast(manifest.manifest_expected_raw_objects as integer) as expected_raw_objects,
        try_cast(manifest.manifest_actual_raw_objects as integer) as actual_raw_objects,
        manifest.manifest_failure_reason as failure_reason
    from latest_manifest_state as manifest
    cross join configured_run
    where manifest.dag_run_id = configured_run.dag_run_id
),

manifest_ranked as (
    select
        *,
        row_number() over (
            order by
                event_at desc nulls last,
                status desc nulls last,
                is_publishable desc nulls last,
                expected_rows desc nulls last,
                actual_rows desc nulls last,
                expected_raw_objects desc nulls last,
                actual_raw_objects desc nulls last,
                failure_reason desc nulls last,
                dag_run_id desc nulls last
        ) as manifest_row_num,
        count(*) over (partition by event_at) as latest_event_tie_count
    from manifest_events
),

manifest_evidence as (
    select
        (select count(*) from manifest_events) as manifest_event_count,
        coalesce(
            max(case when manifest_row_num = 1 then latest_event_tie_count end),
            cast(0 as bigint)
        ) as latest_manifest_event_count,
        max(case when manifest_row_num = 1 then status end) as status,
        max(case when manifest_row_num = 1 then is_publishable end) as is_publishable,
        max(case when manifest_row_num = 1 then event_at end) as manifest_event_at,
        max(case when manifest_row_num = 1 then expected_rows end) as expected_incident_count,
        max(case when manifest_row_num = 1 then actual_rows end) as actual_rows,
        max(case when manifest_row_num = 1 then expected_raw_objects end) as expected_raw_objects,
        max(case when manifest_row_num = 1 then actual_raw_objects end) as actual_raw_objects,
        max(case when manifest_row_num = 1 then failure_reason end) as failure_reason,
        count_if(
            manifest_row_num = 1
            and (
                failure_reason = 'HttpProblemError in land_seoul_traffic_raw'
                or failure_reason = 'ParseError in land_seoul_traffic_raw'
            )
        ) as manifest_clear_api_failure_count,
        count_if(
            manifest_row_num = 1
            and (
                status = 'FAILED'
                or nullif(trim(coalesce(failure_reason, '')), '') is not null
            )
        ) as terminal_manifest_failure_count
    from manifest_ranked
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
    where cast(audit.dag_run_id as varchar) = configured_run.dag_run_id
),

audit_evidence as (
    select
        count(*) as audit_request_count,
        count(distinct request_id) as audit_distinct_request_count,
        count(distinct raw_object_key) as audit_distinct_raw_object_count,
        count_if(
            (http_status is not null and not (http_status between 200 and 299))
            or (result_code is not null and result_code <> 'INFO-000')
        ) as audit_api_failure_count,
        count_if(
            source_id is distinct from 'seoul_traffic_incident'
            or request_id is null
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
        ) as audit_contract_failure_count,
        coalesce(sum(row_count), cast(0 as bigint)) as audited_row_count,
        min(list_total_count) as min_reported_incident_count,
        max(list_total_count) as max_reported_incident_count,
        max(end_index) as max_page_end_index,
        cast(
            at_timezone(
                with_timezone(max(collected_at), 'UTC'),
                'Asia/Seoul'
            ) as timestamp(6)
        ) as audit_snapshot_as_of_at,
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
        cast(bronze.dag_run_id as varchar) as dag_run_id,
        {{ asac_axes.kst_at_from_parts(
            'cast(bronze.occr_date as varchar)',
            'cast(bronze.occr_time as varchar)'
        ) }} as occurred_at
    from {{ source('traffic_bronze', 'seoul_traffic_incident') }} as bronze
    cross join configured_run
    where cast(bronze.dag_run_id as varchar) = configured_run.dag_run_id
),

bronze_evidence as (
    select
        count(*) as bronze_row_count,
        count(distinct source_record_id) as bronze_distinct_incident_count,
        count(distinct raw_object_key) as bronze_distinct_raw_object_count,
        count_if(
            source_id is distinct from 'seoul_traffic_incident'
            or source_record_id is null
            or result_code is distinct from 'INFO-000'
            or raw_object_key is null
            or occurred_at is null
        ) as bronze_contract_failure_count
    from bronze_rows
),

expected_bronze_ids as (
    select distinct source_record_id
    from bronze_rows
    where source_id = 'seoul_traffic_incident'
      and source_record_id is not null
      and result_code = 'INFO-000'
      and occurred_at is not null
),

current_rows as (
    select
        cast(source_record_id as varchar) as source_record_id,
        cast(source_id as varchar) as source_id,
        cast(dag_run_id as varchar) as dag_run_id,
        cast(admin_dong_code as varchar) as admin_dong_code
    from {{ ref('silver_seoul_traffic_incident_current') }}
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

deduped_current as (
    select source_record_id, source_id, dag_run_id, admin_dong_code
    from current_ranked
    where source_record_id is not null
      and current_row_num = 1
),

actual_current_ids as (
    select distinct source_record_id
    from current_rows
    where source_record_id is not null
),

missing_current_ids as (
    select * from expected_bronze_ids
    except
    select * from actual_current_ids
),

extra_current_ids as (
    select * from actual_current_ids
    except
    select * from expected_bronze_ids
),

duplicate_current_ids as (
    select source_record_id
    from current_rows
    where source_record_id is not null
    group by source_record_id
    having count(*) > 1
),

current_evidence as (
    select
        (select count(*) from missing_current_ids)
            + (select count(*) from extra_current_ids)
            + (select count(*) from duplicate_current_ids)
            + count_if(current_rows.source_record_id is null)
            + count_if(current_rows.dag_run_id is distinct from configured_run.dag_run_id)
            + count_if(current_rows.source_id is distinct from configured_run.source_id)
            as current_mismatch_count
    from current_rows
    cross join configured_run
),

canonical as (
    select
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(admin_dong as varchar) as admin_dong,
        cast(gu_code as varchar) as gu_code,
        cast(gu as varchar) as gu,
        try_cast(revision_date as date) as revision_date
    from {{ asac_axes.pinned_dim_admin_dong() }}
),

canonical_evidence as (
    select
        case when count(*) = 0 then cast(1 as bigint) else cast(0 as bigint) end
            + count_if(
                admin_dong_code is null
                or admin_dong is null
                or gu_code is null
                or gu is null
                or revision_date is null
            )
            + (count(*) - count(distinct admin_dong_code))
            as canonical_failure_count
    from canonical
),

mapping_evidence as (
    select count_if(canonical.admin_dong_code is null) as unmapped_incident_count
    from deduped_current as current
    left join canonical
        on current.admin_dong_code = canonical.admin_dong_code
),

combined_evidence as (
    select
        configured_run.dag_run_id,
        configured_run.source_id,
        manifest_evidence.*,
        audit_evidence.*,
        bronze_evidence.*,
        current_evidence.current_mismatch_count,
        canonical_evidence.canonical_failure_count,
        mapping_evidence.unmapped_incident_count
    from configured_run
    cross join manifest_evidence
    cross join audit_evidence
    cross join bronze_evidence
    cross join current_evidence
    cross join canonical_evidence
    cross join mapping_evidence
),

state_inputs as (
    select
        *,
        manifest_clear_api_failure_count + audit_api_failure_count
            as clear_api_failure_count,
        terminal_manifest_failure_count as terminal_non_api_failure_count,
        case
            when manifest_event_at is null
              or status is distinct from 'SUCCESS'
              or is_publishable is distinct from true
              or expected_incident_count is null
              or expected_incident_count < 0
              or actual_rows is distinct from expected_incident_count
              or expected_raw_objects is null
              or expected_raw_objects <= 0
              or actual_raw_objects is distinct from expected_raw_objects
              or audit_request_count <> expected_raw_objects
              or audit_distinct_request_count <> audit_request_count
              or audit_distinct_raw_object_count <> audit_request_count
              or audit_contract_failure_count > 0
              or audit_duplicate_page_count > 0
              or min_reported_incident_count is distinct from expected_incident_count
              or max_reported_incident_count is distinct from expected_incident_count
              or audited_row_count is distinct from expected_incident_count
              or max_page_end_index is null
              or (
                  expected_incident_count > 0
                  and max_page_end_index < expected_incident_count
              )
              or bronze_row_count is distinct from expected_incident_count
              or bronze_distinct_incident_count is distinct from expected_incident_count
              or bronze_contract_failure_count > 0
              or audited_row_count is distinct from bronze_row_count
              or (
                  expected_incident_count > 0
                  and bronze_distinct_raw_object_count is distinct from expected_raw_objects
              )
                then cast(1 as bigint)
            else cast(0 as bigint)
        end as parity_failure_count
    from combined_evidence
),

classified_state as (
    select
        *,
        case
            when manifest_event_count = 0 then 'missing'
            when latest_manifest_event_count <> 1 then 'partial'
            when clear_api_failure_count > 0 then 'api_failure'
            when terminal_non_api_failure_count > 0 then 'partial'
            when audit_request_count = 0 then 'missing'
            when parity_failure_count > 0 then 'partial'
            when current_mismatch_count > 0 then 'current_mismatch'
            when canonical_failure_count > 0 or unmapped_incident_count > 0 then 'spatial_mapping_incomplete'
            when expected_incident_count = 0 then 'complete_zero'
            else 'complete'
        end as expected_quality_state
    from state_inputs
),

expected as (
    select
        dag_run_id,
        source_id,
        expected_quality_state,
        cast(
            at_timezone(
                with_timezone(manifest_event_at, 'UTC'),
                'Asia/Seoul'
            ) as timestamp(6)
        ) as manifest_event_at_kst,
        case
            when expected_quality_state in ('complete', 'complete_zero')
                then audit_snapshot_as_of_at
            else cast(null as timestamp(6))
        end as expected_snapshot_as_of_at,
        expected_incident_count,
        audited_row_count,
        max_page_end_index,
        unmapped_incident_count
    from classified_state
),

gold_rows as (
    select *
    from {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}
),

gold_time_evidence as (
    select
        count(distinct published_at) as published_at_value_count,
        count_if(published_at is null) as published_at_null_count,
        count(distinct hour_at) as hour_at_value_count,
        count_if(hour_at is null) as hour_at_null_count
    from gold_rows
),

gold_violations as (
    select
        'gold_snapshot_evidence_mismatch' as violation_type,
        gold.product_row_id,
        gold.admin_dong_code,
        gold.quality_state as actual_quality_state,
        expected.expected_quality_state,
        gold.snapshot_as_of_at as actual_snapshot_as_of_at,
        expected.expected_snapshot_as_of_at,
        gold.expected_incident_count as actual_expected_incident_count,
        expected.expected_incident_count,
        gold.audited_row_count as actual_audited_row_count,
        expected.audited_row_count,
        gold.max_page_end_index as actual_max_page_end_index,
        expected.max_page_end_index,
        gold.unmapped_incident_count as actual_unmapped_incident_count,
        expected.unmapped_incident_count
    from gold_rows as gold
    cross join expected
    cross join gold_time_evidence
    where cast(gold.snapshot_dag_run_id as varchar) is distinct from expected.dag_run_id
       or cast(gold.source_id as varchar) is distinct from expected.source_id
       or gold.quality_state is distinct from expected.expected_quality_state
       or gold.status_observed_at is distinct from coalesce(expected.manifest_event_at_kst, gold.published_at)
       or gold.hour_at is distinct from cast(date_trunc('hour', gold.status_observed_at) as timestamp(6))
       or gold_time_evidence.published_at_null_count > 0
       or gold_time_evidence.published_at_value_count <> 1
       or gold_time_evidence.hour_at_null_count > 0
       or gold_time_evidence.hour_at_value_count <> 1
       or gold.snapshot_as_of_at is distinct from expected.expected_snapshot_as_of_at
       or gold.expected_incident_count is distinct from expected.expected_incident_count
       or gold.audited_row_count is distinct from expected.audited_row_count
       or gold.max_page_end_index is distinct from expected.max_page_end_index
       or gold.unmapped_incident_count is distinct from expected.unmapped_incident_count
),

missing_gold as (
    select
        'gold_relation_empty' as violation_type,
        cast(null as varchar) as product_row_id,
        cast(null as varchar) as admin_dong_code,
        cast(null as varchar) as actual_quality_state,
        expected.expected_quality_state,
        cast(null as timestamp(6)) as actual_snapshot_as_of_at,
        expected.expected_snapshot_as_of_at,
        cast(null as bigint) as actual_expected_incident_count,
        expected.expected_incident_count,
        cast(null as bigint) as actual_audited_row_count,
        expected.audited_row_count,
        cast(null as integer) as actual_max_page_end_index,
        expected.max_page_end_index,
        cast(null as bigint) as actual_unmapped_incident_count,
        expected.unmapped_incident_count
    from expected
    where not exists (select 1 from gold_rows)
)

select * from gold_violations
union all
select * from missing_gold
