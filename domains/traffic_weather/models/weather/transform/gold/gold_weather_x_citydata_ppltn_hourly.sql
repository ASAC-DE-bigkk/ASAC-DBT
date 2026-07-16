-- Serving Gold: observed Citydata place crowding with no-hindsight KMA forecast context.
-- Grain: (area_cd, event_at).  Citydata is the anchor; no row means no place
-- observation, not zero population.  Weather is selected only if issued by
-- the Citydata event time.

{{ config(materialized='table') }}

with citydata as (
    select
        cast(area_cd as varchar) as area_cd,
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(event_at as timestamp(6)) as event_at,
        cast(collected_at as timestamp(6)) as citydata_collected_at,
        cast(avg_ppltn as double) as avg_ppltn,
        cast(area_congest_lvl as varchar) as area_congest_lvl
    from {{ source('citydata_gold', 'gold_citydata_ppltn_by_time') }}
    where admin_dong_code is not null
),

weather_candidates as (
    select
        citydata.area_cd,
        citydata.event_at,
        upper(cast(weather.category as varchar)) as category,
        cast(weather.issued_at as timestamp(6)) as issued_at,
        cast(weather.collected_at as timestamp(6)) as collected_at,
        cast(weather.fcst_value_num as double) as value_num,
        cast(weather.fcst_value_raw as varchar) as value_raw,
        row_number() over (
            partition by citydata.area_cd, citydata.event_at, weather.category
            order by weather.issued_at desc, weather.collected_at desc, weather.raw_object_key desc, weather.request_id desc
        ) as weather_row_num
    from citydata
    inner join {{ ref('gold_weather_forecast_by_admin_dong') }} as weather
        on citydata.admin_dong_code = weather.admin_dong_code
       and date_trunc('hour', citydata.event_at) = weather.forecast_at
       and weather.issued_at <= citydata.event_at
),

weather_pivot as (
    select
        area_cd,
        event_at,
        count(distinct category) as weather_category_coverage_count,
        max(issued_at) as weather_issued_at_max,
        max(collected_at) as weather_collected_at_max,
        max(value_num) filter (where category = 'TMP') as temp_c,
        max(value_num) filter (where category = 'REH') as humidity_pct,
        max(value_num) filter (where category = 'WSD') as wind_ms,
        max(value_num) filter (where category = 'POP') as precip_prob_pct,
        max(value_raw) filter (where category = 'SKY') as sky_code,
        max(value_raw) filter (where category = 'PTY') as pty_code
    from weather_candidates
    where weather_row_num = 1
    group by 1, 2
)

select
    concat(citydata.area_cd, '|', to_iso8601(cast(citydata.event_at as timestamp(6)))) as product_row_id,
    citydata.area_cd,
    citydata.admin_dong_code,
    citydata.event_at,
    citydata.citydata_collected_at,
    citydata.avg_ppltn,
    citydata.area_congest_lvl,
    weather_pivot.area_cd is not null as weather_observation_present,
    weather_pivot.weather_category_coverage_count,
    weather_pivot.weather_issued_at_max,
    weather_pivot.weather_collected_at_max,
    weather_pivot.temp_c,
    weather_pivot.humidity_pct,
    weather_pivot.wind_ms,
    weather_pivot.precip_prob_pct,
    weather_pivot.sky_code,
    {{ weather_sky_label('weather_pivot.sky_code') }} as sky_label,
    weather_pivot.pty_code,
    {{ weather_pty_label('weather_pivot.pty_code') }} as pty_label,
    (weather_pivot.pty_code is not null and weather_pivot.pty_code <> '0') as is_precipitating
from citydata
left join weather_pivot
    on citydata.area_cd = weather_pivot.area_cd
   and citydata.event_at = weather_pivot.event_at
