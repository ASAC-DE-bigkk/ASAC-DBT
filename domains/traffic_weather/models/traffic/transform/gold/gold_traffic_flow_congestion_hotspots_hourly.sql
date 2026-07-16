-- Serving Gold: observed low-speed road-link hotspots by KST hour.
-- Grain: (hour_at, link_id).  Rank compares only the observed link snapshot,
-- not an absolute congestion level or road-class-adjusted benchmark.

{{ config(materialized='table') }}

with flow_history as (
    select
        cast(link_id as varchar) as link_id,
        cast(flow_speed as double) as flow_speed,
        cast(flow_travel_time as double) as flow_travel_time,
        cast(flow_value_quality as varchar) as flow_value_quality,
        cast(observed_at as timestamp(6)) as observed_at_utc,
        cast({{ asac_axes.utc_to_kst('observed_at') }} as timestamp(6)) as observed_at_kst,
        cast(raw_object_key as varchar) as raw_object_key,
        cast(payload_hash as varchar) as payload_hash,
        cast(dag_run_id as varchar) as dag_run_id
    from {{ ref('silver_seoul_traffic_flow') }}
),

ranked_link_hour as (
    select
        *,
        date_trunc('hour', observed_at_kst) as hour_at,
        row_number() over (
            partition by link_id, date_trunc('hour', observed_at_kst)
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
