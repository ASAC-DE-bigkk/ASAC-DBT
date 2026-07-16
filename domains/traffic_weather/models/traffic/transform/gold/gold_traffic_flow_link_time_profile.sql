-- Serving Gold: observed TrafficInfo rhythm by road link, KST weekday, and hour.
-- Grain: (link_id, kst_day_of_week, kst_hour).  It is a descriptive profile,
-- and sparse observation cells stay sparse instead of being zero-filled.

{{ config(materialized='table') }}

with flow_history as (
    select
        cast(link_id as varchar) as link_id,
        cast(flow_speed as double) as flow_speed,
        cast(flow_travel_time as double) as flow_travel_time,
        cast({{ asac_axes.utc_to_kst('observed_at') }} as timestamp(6)) as observed_at_kst
    from {{ ref('silver_seoul_traffic_flow') }}
)

select
    concat(
        link_id, '|',
        cast(day_of_week(observed_at_kst) as varchar), '|',
        cast(hour(observed_at_kst) as varchar)
    ) as product_row_id,
    link_id,
    day_of_week(observed_at_kst) as kst_day_of_week,
    hour(observed_at_kst) as kst_hour,
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
