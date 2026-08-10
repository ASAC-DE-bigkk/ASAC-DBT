-- Serving Gold: observed low-speed road-link hotspots by KST hour.
-- Incremental path recalculates all link ranks for hours touched by the pinned Flow run.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['hour_at', 'link_id'],
    on_table_exists='drop',
    on_schema_change='fail',
    views_enabled=false,
    pre_hook="{{ traffic_flow_assert_pinned_incremental_rows() }}"
) }}

with changed_hours as (
    {{ traffic_flow_changed_hours() }}
),

flow_history as (
    select
        cast(link_id as varchar) as link_id,
        cast(flow_speed as double) as flow_speed,
        cast(flow_travel_time as double) as flow_travel_time,
        cast(flow_value_quality as varchar) as flow_value_quality,
        cast(observed_at as timestamp(6)) as observed_at_utc,
        cast({{ asac_axes.utc_to_kst('observed_at') }} as timestamp(6)) as observed_at_kst,
        cast(date_trunc('hour', {{ asac_axes.utc_to_kst('observed_at') }}) as timestamp(6)) as hour_at,
        cast(request_id as varchar) as request_id,
        cast(raw_object_key as varchar) as raw_object_key,
        cast(payload_hash as varchar) as payload_hash,
        cast(parent_incident_run_id as varchar) as parent_incident_run_id,
        cast(dag_run_id as varchar) as dag_run_id
    from {{ ref('silver_seoul_traffic_flow') }} as flow
    {% if is_incremental() %}
    inner join changed_hours
        on cast(date_trunc('hour', {{ asac_axes.utc_to_kst('flow.observed_at') }}) as timestamp(6)) = changed_hours.hour_at
    {% endif %}
),

ranked_link_hour as (
    select
        *,
        row_number() over (
            partition by link_id, hour_at
            order by observed_at_utc desc, raw_object_key desc, request_id desc
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
    concat(
        ranked_hotspots.link_id,
        '|',
        to_iso8601(cast(ranked_hotspots.hour_at as timestamp(6)))
    ) as product_row_id,
    ranked_hotspots.link_id,
    ranked_hotspots.hour_at,
    ranked_hotspots.flow_speed,
    ranked_hotspots.flow_travel_time,
    ranked_hotspots.flow_value_quality,
    ranked_hotspots.observed_at_kst,
    ranked_hotspots.congestion_rank,
    ranked_hotspots.observed_link_count,
    case
        when ranked_hotspots.flow_speed is null then 'missing_speed'
        when ranked_hotspots.congestion_rank <= 10 then 'lowest_speed_top_10'
        else 'observed'
    end as hotspot_state,
    cast(road.road_name as varchar) as road_name,
    cast(road.start_node_name as varchar) as start_node_name,
    cast(road.end_node_name as varchar) as end_node_name,
    cast(road.map_distance as double) as map_distance,
    cast(road.representative_vertex_sequence as integer) as representative_vertex_sequence,
    cast(road.longitude as double) as longitude,
    cast(road.latitude as double) as latitude,
    cast(road.admin_dong_code as varchar) as admin_dong_code,
    cast(road.admin_dong as varchar) as admin_dong,
    cast(road.gu_code as varchar) as gu_code,
    cast(road.gu as varchar) as gu,
    cast(coalesce(road.link_reference_quality, 'missing_info') as varchar)
        as link_reference_quality,
    cast(
        {{ asac_axes.utc_to_kst('road.reference_collected_at') }}
        as timestamp(6)
    ) as link_reference_collected_at_kst,
    ranked_hotspots.raw_object_key,
    ranked_hotspots.payload_hash,
    ranked_hotspots.parent_incident_run_id,
    ranked_hotspots.dag_run_id
from ranked_hotspots
left join {{ ref('silver_seoul_traffic_link_reference') }} as road
  on ranked_hotspots.link_id = road.link_id
