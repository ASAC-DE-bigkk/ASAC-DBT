-- Serving Gold: latest active-incident mix by TOPIS type and detail type.
-- Grain: (acc_type, acc_dtype), with null source labels retained as __UNKNOWN__.

{{ config(materialized='table') }}

with incidents as (
    select *
    from {{ ref('gold_traffic_incident_active_latest') }}
)

select
    concat(
        coalesce(acc_type, '__UNKNOWN__'),
        '|',
        coalesce(acc_dtype, '__UNKNOWN__')
    ) as product_row_id,
    coalesce(acc_type, '__UNKNOWN__') as acc_type,
    coalesce(acc_dtype, '__UNKNOWN__') as acc_dtype,
    count(*) as incident_count,
    count_if(link_id is not null) as link_identified_incident_count,
    count_if(admin_dong_code is not null) as admin_dong_mapped_incident_count,
    count_if(expected_clear_at is not null) as expected_clearance_present_count,
    min(occurred_at) as first_occurred_at,
    max(occurred_at) as last_occurred_at,
    max(snapshot_observed_at) as snapshot_observed_at,
    max(snapshot_dag_run_id) as snapshot_dag_run_id
from incidents
group by 1, 2, 3
