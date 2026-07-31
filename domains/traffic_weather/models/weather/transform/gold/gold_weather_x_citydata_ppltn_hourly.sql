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

weather_winners as (
    select
        citydata.area_cd,
        citydata.event_at,
        upper(cast(weather.category as varchar)) as category,
        max_by(
            cast(row(
                cast(weather.issued_at as timestamp(6)),
                cast(weather.collected_at as timestamp(6)),
                cast(weather.fcst_value_num as double),
                cast(weather.fcst_value_raw as varchar)
            ) as row(
                issued_at timestamp(6),
                collected_at timestamp(6),
                value_num double,
                value_raw varchar
            )),
            row(
                cast(weather.issued_at as timestamp(6)),
                cast(weather.collected_at as timestamp(6)),
                cast(weather.raw_object_key as varchar),
                cast(weather.request_id as varchar)
            )
        ) as winner
    from citydata
    inner join {{ ref('gold_weather_forecast_by_admin_dong') }} as weather
        on citydata.admin_dong_code = weather.admin_dong_code
       and date_trunc('hour', citydata.event_at) = weather.forecast_at
       and weather.issued_at <= citydata.event_at
    group by citydata.area_cd, citydata.event_at, upper(cast(weather.category as varchar))
),

weather_pivot as (
    select
        area_cd,
        event_at,
        count(distinct category) as weather_category_coverage_count,
        max(winner.issued_at) as weather_issued_at_max,
        max(winner.collected_at) as weather_collected_at_max,
        max(winner.value_num) filter (where category = 'TMP') as temp_c,
        max(winner.value_num) filter (where category = 'REH') as humidity_pct,
        max(winner.value_num) filter (where category = 'WSD') as wind_ms,
        max(winner.value_num) filter (where category = 'POP') as precip_prob_pct,
        max(winner.value_raw) filter (where category = 'SKY') as sky_code,
        max(winner.value_raw) filter (where category = 'PTY') as pty_code
    from weather_winners
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
