-- Serving Gold: nearest future mapped-place forecast with as-of Citydata live context.
-- Grain: place_id.  Signal timestamps remain separate; refreshed_at is used as
-- a cutoff so a later Citydata snapshot is not attached to an earlier KMA issue.

{{ config(materialized='table') }}

with weather as (
    select *
    from {{ ref('gold_weather_place_current_outlook') }}
),

citydata_candidates as (
    select
        weather.place_id,
        cast(citydata.area_cd as varchar) as area_cd,
        cast(citydata.area_congest_lvl as varchar) as area_congest_lvl,
        cast(citydata.area_ppltn_min as double) as area_ppltn_min,
        cast(citydata.area_ppltn_max as double) as area_ppltn_max,
        cast(citydata.payment_count as double) as payment_count,
        cast(citydata.subway_gton_30min as double) as subway_gton_30min,
        cast(citydata.bus_gton_30min as double) as bus_gton_30min,
        cast(citydata.sbike_parking_total as double) as sbike_parking_total,
        cast(citydata.sbike_rack_total as double) as sbike_rack_total,
        cast(citydata.ppltn_at as timestamp(6)) as ppltn_at,
        cast(citydata.cmrcl_at as timestamp(6)) as cmrcl_at,
        cast(citydata.transit_at as timestamp(6)) as transit_at,
        cast(citydata.sbike_at as timestamp(6)) as sbike_at,
        cast(citydata.refreshed_at as timestamp(6)) as refreshed_at
    from weather
    inner join {{ source('citydata_gold', 'gold_citydata_place_latest') }} as citydata
        on weather.admin_dong_code = citydata.admin_dong_code
       and citydata.refreshed_at <= weather.forecast_issued_at_max
),

citydata_by_place as (
    select
        place_id,
        count(distinct area_cd) as monitored_place_count,
        avg((area_ppltn_min + area_ppltn_max) / 2) as avg_place_population_proxy,
        max((area_ppltn_min + area_ppltn_max) / 2) as peak_place_population_proxy,
        sum(payment_count) as payment_count_sum,
        sum(subway_gton_30min) as subway_gton_30min_sum,
        sum(bus_gton_30min) as bus_gton_30min_sum,
        sum(sbike_parking_total) as sbike_parking_total_sum,
        sum(sbike_rack_total) as sbike_rack_total_sum,
        max(ppltn_at) as citydata_latest_ppltn_at,
        max(cmrcl_at) as citydata_latest_cmrcl_at,
        max(transit_at) as citydata_latest_transit_at,
        max(sbike_at) as citydata_latest_sbike_at,
        max(refreshed_at) as citydata_latest_refreshed_at
    from citydata_candidates
    group by 1
)

select
    weather.place_id as product_row_id,
    weather.place_id,
    weather.place_name,
    weather.alias_names,
    weather.admin_dong_code,
    weather.admin_dong,
    weather.gu_code,
    weather.gu,
    weather.forecast_at,
    weather.forecast_issued_at_max as weather_as_of_at,
    weather.temp_c,
    weather.humidity_pct,
    weather.wind_ms,
    weather.precip_prob_pct,
    weather.sky_code,
    weather.sky_label,
    weather.pty_code,
    weather.pty_label,
    weather.is_precipitating,
    citydata_by_place.place_id is not null as citydata_observation_present,
    citydata_by_place.monitored_place_count,
    citydata_by_place.avg_place_population_proxy,
    citydata_by_place.peak_place_population_proxy,
    citydata_by_place.payment_count_sum,
    citydata_by_place.subway_gton_30min_sum,
    citydata_by_place.bus_gton_30min_sum,
    citydata_by_place.sbike_parking_total_sum,
    citydata_by_place.sbike_rack_total_sum,
    citydata_by_place.citydata_latest_ppltn_at,
    citydata_by_place.citydata_latest_cmrcl_at,
    citydata_by_place.citydata_latest_transit_at,
    citydata_by_place.citydata_latest_sbike_at,
    citydata_by_place.citydata_latest_refreshed_at,
    'not_exposed_by_upstream_gold' as external_freshness_status
from weather
left join citydata_by_place
    on weather.place_id = citydata_by_place.place_id
