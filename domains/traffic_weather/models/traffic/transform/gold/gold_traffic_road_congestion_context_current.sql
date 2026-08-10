-- Flow-anchored current road context with exact-parent Incident and no-hindsight Weather.
-- Grain: one row per latest Flow link_id. Missing context never removes a Flow row.

{{ config(materialized='table') }}

{% set incident_snapshot_dag_run_id = var('traffic_snapshot_dag_run_id', '') or '' %}

with flow as (
    select
        cast(product_row_id as varchar) as product_row_id,
        cast(link_id as varchar) as link_id,
        cast(road_name as varchar) as road_name,
        cast(start_node_name as varchar) as start_node_name,
        cast(end_node_name as varchar) as end_node_name,
        cast(map_distance as double) as map_distance,
        cast(representative_vertex_sequence as integer) as representative_vertex_sequence,
        cast(longitude as double) as longitude,
        cast(latitude as double) as latitude,
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(admin_dong as varchar) as admin_dong,
        cast(gu_code as varchar) as gu_code,
        cast(gu as varchar) as gu,
        cast(link_reference_quality as varchar) as link_reference_quality,
        cast(flow_speed as double) as flow_speed,
        cast(flow_travel_time as double) as flow_travel_time,
        cast(flow_value_quality as varchar) as flow_value_quality,
        cast(observed_at_kst as timestamp(6)) as observed_at_kst,
        cast(date_trunc('hour', observed_at_kst) as timestamp(6)) as observed_hour_at,
        cast(collected_at_kst as timestamp(6)) as collected_at_kst,
        cast(parent_incident_run_id as varchar) as parent_incident_run_id,
        cast(dag_run_id as varchar) as flow_dag_run_id
    from {{ ref('gold_traffic_flow_link_latest') }}
),

hotspot as (
    select
        cast(link_id as varchar) as link_id,
        cast(hour_at as timestamp(6)) as hour_at,
        cast(congestion_rank as bigint) as congestion_rank,
        cast(observed_link_count as bigint) as observed_link_count,
        cast(hotspot_state as varchar) as hotspot_state
    from {{ ref('gold_traffic_flow_congestion_hotspots_hourly') }}
),

current_run as (
    select cast(
        '{{ incident_snapshot_dag_run_id | replace("'", "''") }}'
        as varchar
    ) as dag_run_id
),

incident as (
    select
        cast(source_record_id as varchar) as source_record_id,
        cast(asset_id as varchar) as asset_id,
        cast(acc_type as varchar) as incident_type,
        cast(acc_dtype as varchar) as incident_detail_type,
        cast(acc_info as varchar) as incident_description,
        cast(occurred_at as timestamp(6)) as occurred_at_kst,
        cast(expected_clear_at as timestamp(6)) as expected_clear_at_kst,
        cast(dag_run_id as varchar) as dag_run_id
    from {{ ref('silver_seoul_traffic_incident_current') }}
),

incident_candidates as (
    select
        flow.product_row_id,
        incident.source_record_id,
        incident.incident_type,
        incident.incident_detail_type,
        incident.incident_description,
        incident.occurred_at_kst,
        incident.expected_clear_at_kst,
        incident.dag_run_id,
        count(*) over (partition by flow.product_row_id) as incident_count,
        row_number() over (
            partition by flow.product_row_id
            order by incident.occurred_at_kst desc, incident.source_record_id desc
        ) as incident_row_num
    from flow
    inner join incident
        on incident.asset_id = flow.link_id
       and incident.dag_run_id = flow.parent_incident_run_id
),

incident_hourly as (
    select
        product_row_id,
        cast(incident_count as bigint) as incident_count,
        incident_type as latest_incident_type,
        incident_detail_type as latest_incident_detail_type,
        incident_description as latest_incident_description,
        occurred_at_kst as latest_incident_occurred_at_kst,
        expected_clear_at_kst as latest_incident_expected_clear_at_kst
    from incident_candidates
    where incident_row_num = 1
),

weather_bridge_ranked as (
    select
        cast(source_admin_code as varchar) as admin_dong_code,
        cast(nx as integer) as nx,
        cast(ny as integer) as ny,
        row_number() over (
            partition by cast(source_admin_code as varchar)
            order by
                cast(grid_distance_m as double) asc nulls last,
                cast(nx as integer),
                cast(ny as integer)
        ) as bridge_row_num
    from {{ ref('bridge_weather_admin_dong_grid') }}
    where cast(bridge_version as varchar) = 'weather_admin_dong_grid_bridge_v1'
      and cast(canonical_join_eligible as boolean)
),

weather_bridge as (
    select admin_dong_code, nx, ny
    from weather_bridge_ranked
    where bridge_row_num = 1
),

weather_history as (
    select
        cast(nx as integer) as nx,
        cast(ny as integer) as ny,
        cast(source_grid_place_id as varchar) as source_grid_place_id,
        cast(issued_at as timestamp(6)) as issued_at,
        cast(forecast_at as timestamp(6)) as forecast_at,
        lower(cast(category as varchar)) as category,
        cast(collected_at as timestamp(6)) as collected_at,
        cast(value_num as double) as value_num,
        cast(qualitative_code as varchar) as qualitative_code,
        cast(raw_object_key as varchar) as raw_object_key,
        cast(request_id as varchar) as request_id,
        cast(selected_dag_run_id as varchar) as dag_run_id
    from {{ ref('silver_kma_vilage_fcst_grid') }}
    where issued_at is not null
),

weather_candidates as (
    select
        flow.product_row_id,
        weather.category,
        weather.issued_at,
        weather.collected_at,
        weather.value_num,
        weather.qualitative_code,
        row_number() over (
            partition by flow.product_row_id, lower(weather.category)
            order by {{ weather_w2_grid_winner_order_key('weather') }} desc
        ) as category_row_num
    from flow
    inner join weather_bridge
        on flow.admin_dong_code = weather_bridge.admin_dong_code
    inner join weather_history as weather
        on weather_bridge.nx = weather.nx
       and weather_bridge.ny = weather.ny
       and cast(date_trunc('hour', weather.forecast_at) as timestamp(6))
            = flow.observed_hour_at
       and weather.issued_at <= flow.observed_at_kst
    where lower(weather.category) in ('tmp', 'pop', 'reh', 'wsd', 'sky', 'pty')
),

latest_weather_category as (
    select
        product_row_id,
        category,
        issued_at,
        collected_at,
        value_num,
        qualitative_code
    from weather_candidates
    where category_row_num = 1
),

weather_hourly as (
    select
        product_row_id,
        count(distinct category) as weather_category_coverage_count,
        max(issued_at) as weather_latest_issued_at,
        max(collected_at) as weather_latest_collected_at,
        max(case when category = 'tmp' then value_num end) as tmp_value_num,
        max(case when category = 'pop' then value_num end) as pop_value_num,
        max(case when category = 'reh' then value_num end) as reh_value_num,
        max(case when category = 'wsd' then value_num end) as wsd_value_num,
        max(case when category = 'sky' then qualitative_code end) as sky_qualitative_code,
        max(case when category = 'pty' then qualitative_code end) as pty_qualitative_code,
        case
            when count_if(category = 'pty') = 0 then cast(null as boolean)
            when max(case when category = 'pty' then qualitative_code end) = '0'
                then false
            when max(case when category = 'pty' then qualitative_code end)
                in ('1', '2', '3', '4', '5', '6', '7')
                then true
            else cast(null as boolean)
        end as is_precipitating
    from latest_weather_category
    group by product_row_id
)

select
    cast(flow.product_row_id as varchar) as product_row_id,
    cast(flow.link_id as varchar) as link_id,
    cast(flow.road_name as varchar) as road_name,
    cast(flow.start_node_name as varchar) as start_node_name,
    cast(flow.end_node_name as varchar) as end_node_name,
    cast(flow.map_distance as double) as map_distance,
    cast(flow.representative_vertex_sequence as integer) as representative_vertex_sequence,
    cast(flow.longitude as double) as longitude,
    cast(flow.latitude as double) as latitude,
    cast(flow.admin_dong_code as varchar) as admin_dong_code,
    cast(flow.admin_dong as varchar) as admin_dong,
    cast(flow.gu_code as varchar) as gu_code,
    cast(flow.gu as varchar) as gu,
    cast(flow.link_reference_quality as varchar) as link_reference_quality,
    cast(flow.flow_speed as double) as flow_speed,
    cast(flow.flow_travel_time as double) as flow_travel_time,
    cast(flow.flow_value_quality as varchar) as flow_value_quality,
    cast(flow.observed_at_kst as timestamp(6)) as observed_at_kst,
    cast(flow.collected_at_kst as timestamp(6)) as collected_at_kst,
    cast(flow.parent_incident_run_id as varchar) as parent_incident_run_id,
    cast(hotspot.congestion_rank as bigint) as congestion_rank,
    cast(hotspot.observed_link_count as bigint) as observed_link_count,
    cast(hotspot.hotspot_state as varchar) as hotspot_state,
    cast(coalesce(incident_hourly.incident_count, 0) as bigint) as incident_count,
    cast(incident_hourly.latest_incident_type as varchar) as latest_incident_type,
    cast(incident_hourly.latest_incident_detail_type as varchar)
        as latest_incident_detail_type,
    cast(incident_hourly.latest_incident_description as varchar)
        as latest_incident_description,
    cast(incident_hourly.latest_incident_occurred_at_kst as timestamp(6))
        as latest_incident_occurred_at_kst,
    cast(incident_hourly.latest_incident_expected_clear_at_kst as timestamp(6))
        as latest_incident_expected_clear_at_kst,
    cast(case
        when flow.parent_incident_run_id is null
          or trim(flow.parent_incident_run_id) = ''
            then 'missing_parent_lineage'
        when incident_hourly.product_row_id is not null
            then 'matched_exact_parent'
        when current_run.dag_run_id = flow.parent_incident_run_id
            then 'no_incident_in_exact_parent'
        else 'parent_snapshot_not_current'
    end as varchar) as incident_context_state,
    cast(coalesce(weather_hourly.weather_category_coverage_count, 0) as bigint)
        as weather_category_coverage_count,
    cast(weather_hourly.weather_latest_issued_at as timestamp(6))
        as weather_latest_issued_at,
    cast(weather_hourly.weather_latest_collected_at as timestamp(6))
        as weather_latest_collected_at,
    cast(weather_hourly.tmp_value_num as double) as tmp_value_num,
    cast(weather_hourly.pop_value_num as double) as pop_value_num,
    cast(weather_hourly.reh_value_num as double) as reh_value_num,
    cast(weather_hourly.wsd_value_num as double) as wsd_value_num,
    cast(weather_hourly.sky_qualitative_code as varchar) as sky_qualitative_code,
    cast(weather_hourly.pty_qualitative_code as varchar) as pty_qualitative_code,
    cast(weather_hourly.is_precipitating as boolean) as is_precipitating,
    cast(case
        when flow.admin_dong_code is null then 'missing_link_location'
        when weather_bridge.admin_dong_code is null then 'missing_weather_bridge'
        when coalesce(weather_hourly.weather_category_coverage_count, 0) = 0
            then 'missing_weather_context'
        when weather_hourly.weather_category_coverage_count < 6
            then 'partial_weather_context'
        else 'available'
    end as varchar) as weather_context_state,
    cast(flow.flow_dag_run_id as varchar) as flow_dag_run_id
from flow
left join hotspot
    on flow.link_id = hotspot.link_id
   and flow.observed_hour_at = hotspot.hour_at
left join current_run
    on true
left join incident_hourly
    on flow.product_row_id = incident_hourly.product_row_id
left join weather_bridge
    on flow.admin_dong_code = weather_bridge.admin_dong_code
left join weather_hourly
    on flow.product_row_id = weather_hourly.product_row_id
