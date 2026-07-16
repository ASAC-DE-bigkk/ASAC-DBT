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
