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
