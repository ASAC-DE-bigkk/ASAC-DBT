-- Serving Gold: incident-level expected-clearance watchlist.
-- This is source expectation evidence, not measured clearance duration or SLA.

{{ config(materialized='table') }}

with incidents as (
    select *
    from {{ ref('gold_traffic_incident_active_latest') }}
)

select
    source_record_id as product_row_id,
    source_record_id,
    source_id,
    acc_type,
    acc_dtype,
    link_id,
    acc_road_code,
    acc_info,
    admin_dong_code,
    admin_dong,
    gu_code,
    gu,
    occurred_at,
    expected_clear_at,
    snapshot_observed_at,
    case
        when expected_clear_at is null then 'missing_expected_clearance'
        when occurred_at is null then 'missing_occurrence_time'
        when expected_clear_at < occurred_at then 'invalid_expected_clearance'
        when expected_clear_at <= snapshot_observed_at then 'past_expected_clearance'
        else 'future_expected_clearance'
    end as expected_clearance_state,
    case
        when expected_clear_at >= occurred_at
            then date_diff('minute', occurred_at, expected_clear_at)
    end as expected_clearance_lead_minutes,
    raw_object_key,
    payload_hash,
    collected_at_utc,
    snapshot_dag_run_id
from incidents
