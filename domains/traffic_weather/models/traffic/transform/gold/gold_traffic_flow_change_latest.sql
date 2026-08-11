-- Serving Gold: latest per-link speed and travel-time change versus its prior observation.
-- Incremental path recalculates full history only for links touched by the pinned Flow run.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key='link_id',
    on_table_exists='drop',
    views_enabled=false,
    pre_hook="{{ traffic_flow_assert_pinned_incremental_rows() }}"
) }}

with changed_links as (
    {{ traffic_flow_changed_links() }}
),

scoped_history as (
    select flow.*
    from {{ ref('silver_seoul_traffic_flow') }} as flow
    {% if is_incremental() %}
    inner join changed_links
        on cast(flow.link_id as varchar) = changed_links.link_id
    {% endif %}
),

ordered_history as (
    select
        cast(link_id as varchar) as link_id,
        cast(flow_speed as double) as flow_speed,
        cast(flow_travel_time as double) as flow_travel_time,
        cast(flow_value_quality as varchar) as flow_value_quality,
        cast(observed_at as timestamp(6)) as observed_at_utc,
        cast({{ asac_axes.utc_to_kst('observed_at') }} as timestamp(6)) as observed_at_kst,
        cast(raw_object_key as varchar) as raw_object_key,
        cast(payload_hash as varchar) as payload_hash,
        cast(dag_run_id as varchar) as dag_run_id,
        lag(flow_speed) over (
            partition by link_id
            order by observed_at, raw_object_key, request_id
        ) as previous_flow_speed,
        lag(flow_travel_time) over (
            partition by link_id
            order by observed_at, raw_object_key, request_id
        ) as previous_flow_travel_time,
        lag(observed_at) over (
            partition by link_id
            order by observed_at, raw_object_key, request_id
        ) as previous_observed_at_utc,
        row_number() over (
            partition by link_id
            order by observed_at desc, raw_object_key desc, request_id desc
        ) as latest_row_num
    from scoped_history
)

select
    ordered_history.link_id as product_row_id,
    ordered_history.link_id,
    cast(road.road_name as varchar) as road_name,
    cast(road.admin_dong_code as varchar) as admin_dong_code,
    cast(road.admin_dong as varchar) as admin_dong,
    cast(road.gu_code as varchar) as gu_code,
    cast(road.gu as varchar) as gu,
    cast(coalesce(road.link_reference_quality, 'missing_info') as varchar)
        as link_reference_quality,
    flow_speed,
    flow_travel_time,
    flow_value_quality,
    observed_at_utc,
    observed_at_kst,
    previous_flow_speed,
    previous_flow_travel_time,
    cast({{ asac_axes.utc_to_kst('previous_observed_at_utc') }} as timestamp(6)) as previous_observed_at_kst,
    case
        when flow_speed is not null and previous_flow_speed is not null
            then flow_speed - previous_flow_speed
    end as flow_speed_change,
    case
        when flow_travel_time is not null and previous_flow_travel_time is not null
            then flow_travel_time - previous_flow_travel_time
    end as flow_travel_time_change,
    case
        when previous_observed_at_utc is null then 'no_prior_observation'
        when flow_speed is null or previous_flow_speed is null then 'speed_unavailable'
        when flow_speed < previous_flow_speed then 'speed_decreased'
        when flow_speed > previous_flow_speed then 'speed_increased'
        else 'speed_unchanged'
    end as speed_change_state,
    raw_object_key,
    payload_hash,
    dag_run_id
from ordered_history
left join {{ ref('silver_seoul_traffic_link_reference') }} as road
  on ordered_history.link_id = road.link_id
where latest_row_num = 1
