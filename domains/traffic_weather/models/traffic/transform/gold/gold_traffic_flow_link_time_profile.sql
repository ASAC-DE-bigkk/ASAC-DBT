-- Serving Gold: observed TrafficInfo rhythm by road link, KST weekday, and hour.
-- Incremental path recalculates profile cells touched by the pinned Flow run.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['link_id', 'kst_day_of_week', 'kst_hour'],
    on_table_exists='drop',
    on_schema_change='fail',
    views_enabled=false,
    pre_hook="{{ traffic_flow_assert_pinned_incremental_rows() }}"
) }}

with changed_profile_keys as (
    {{ traffic_flow_changed_profile_keys() }}
),

flow_history as (
    select
        cast(flow.link_id as varchar) as link_id,
        cast(flow.flow_speed as double) as flow_speed,
        cast(flow.flow_travel_time as double) as flow_travel_time,
        cast({{ asac_axes.utc_to_kst('flow.observed_at') }} as timestamp(6)) as observed_at_kst,
        day_of_week(cast({{ asac_axes.utc_to_kst('flow.observed_at') }} as timestamp(6))) as kst_day_of_week,
        hour(cast({{ asac_axes.utc_to_kst('flow.observed_at') }} as timestamp(6))) as kst_hour
    from {{ ref('silver_seoul_traffic_flow') }} as flow
    {% if is_incremental() %}
    inner join changed_profile_keys
        on cast(flow.link_id as varchar) = changed_profile_keys.link_id
       and day_of_week(cast({{ asac_axes.utc_to_kst('flow.observed_at') }} as timestamp(6))) = changed_profile_keys.kst_day_of_week
       and hour(cast({{ asac_axes.utc_to_kst('flow.observed_at') }} as timestamp(6))) = changed_profile_keys.kst_hour
    {% endif %}
),

profile as (
    select
        concat(
            link_id, '|',
            cast(kst_day_of_week as varchar), '|',
            cast(kst_hour as varchar)
        ) as product_row_id,
        link_id,
        kst_day_of_week,
        kst_hour,
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
)

select
    profile.product_row_id,
    profile.link_id,
    cast(road.road_name as varchar) as road_name,
    cast(road.admin_dong_code as varchar) as admin_dong_code,
    cast(road.admin_dong as varchar) as admin_dong,
    cast(road.gu_code as varchar) as gu_code,
    cast(road.gu as varchar) as gu,
    cast(coalesce(road.link_reference_quality, 'missing_info') as varchar)
        as link_reference_quality,
    profile.kst_day_of_week,
    profile.kst_hour,
    profile.observation_count,
    profile.speed_observation_count,
    profile.avg_flow_speed,
    profile.min_flow_speed,
    profile.max_flow_speed,
    profile.avg_flow_travel_time,
    profile.first_observed_at_kst,
    profile.last_observed_at_kst
from profile
left join {{ ref('silver_seoul_traffic_link_reference') }} as road
  on profile.link_id = road.link_id
