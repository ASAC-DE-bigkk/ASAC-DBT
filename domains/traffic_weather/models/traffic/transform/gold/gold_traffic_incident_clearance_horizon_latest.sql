-- Serving Gold: latest TOPIS expected-clearance distribution.
-- Grain: expected_clearance_horizon.  It preserves source expectations only;
-- it does not infer actual clearance, recovery, or an operations SLA.

{{ config(materialized='table') }}

with watchlist as (
    select *
    from {{ ref('gold_traffic_incident_clearance_watchlist') }}
),

bucketed as (
    select
        *,
        case
            when expected_clearance_state = 'future_expected_clearance'
             and expected_clear_at <= snapshot_observed_at + interval '30' minute
                then 'future_within_30m'
            when expected_clearance_state = 'future_expected_clearance'
             and expected_clear_at <= snapshot_observed_at + interval '60' minute
                then 'future_31_to_60m'
            when expected_clearance_state = 'future_expected_clearance'
                then 'future_over_60m'
            else expected_clearance_state
        end as expected_clearance_horizon
    from watchlist
)

select
    expected_clearance_horizon as product_row_id,
    expected_clearance_horizon,
    count(*) as incident_count,
    count_if(link_id is not null) as link_identified_incident_count,
    count_if(admin_dong_code is not null) as admin_dong_mapped_incident_count,
    min(occurred_at) as first_occurred_at,
    min(expected_clear_at) as nearest_expected_clear_at,
    max(expected_clear_at) as latest_expected_clear_at,
    max(snapshot_observed_at) as snapshot_observed_at,
    max(collected_at_utc) as collected_at_utc,
    max(snapshot_dag_run_id) as snapshot_dag_run_id
from bucketed
group by 1, 2
