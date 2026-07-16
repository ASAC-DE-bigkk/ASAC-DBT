-- Serving Gold: most recently observed TrafficInfo row per road link.
-- Grain: link_id; observed_at_utc is the source collection timestamp.

{{ config(materialized='table') }}

with ranked as (
    select
        flow.*,
        row_number() over (
            partition by flow.link_id
            order by flow.observed_at desc, flow.raw_object_key desc, flow.request_id desc
        ) as row_num
    from {{ ref('silver_seoul_traffic_flow') }} as flow
)

select
    cast(link_id as varchar) as product_row_id,
    cast(link_id as varchar) as link_id,
    cast(source_id as varchar) as source_id,
    cast(flow_speed as double) as flow_speed,
    cast(flow_travel_time as double) as flow_travel_time,
    cast(flow_value_quality as varchar) as flow_value_quality,
    cast(observed_at as timestamp(6)) as observed_at_utc,
    cast({{ asac_axes.utc_to_kst('observed_at') }} as timestamp(6)) as observed_at_kst,
    cast(raw_object_key as varchar) as raw_object_key,
    cast(payload_hash as varchar) as payload_hash,
    cast(request_id as varchar) as request_id,
    cast(collected_at as timestamp(6)) as collected_at_utc,
    cast(dag_run_id as varchar) as dag_run_id
from ranked
where row_num = 1
