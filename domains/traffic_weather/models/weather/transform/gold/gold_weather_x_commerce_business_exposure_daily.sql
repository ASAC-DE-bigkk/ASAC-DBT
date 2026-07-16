with weather as (
    select
        daily.product_row_id as weather_daily_product_row_id,
        daily.admin_dong_code,
        daily.forecast_date,
        daily.admin_dong,
        daily.gu_code,
        daily.gu,
        daily.temp_min_c,
        daily.temp_max_c,
        daily.temp_avg_c,
        daily.precip_prob_max_pct,
        daily.humidity_avg_pct,
        daily.wind_avg_ms,
        daily.wind_max_ms,
        daily.precip_hours,
        daily.snow_hours,
        daily.forecast_hours
    from {{ ref('gold_weather_daily_by_admin_dong') }} as daily
),

weather_lineage as (
    select
        admin_dong_code,
        date(forecast_at) as forecast_date,
        min(issued_at) as weather_issued_at_min,
        max(issued_at) as weather_issued_at_max,
        max(collected_at) as weather_collected_at_max,
        max(published_at) as weather_published_at_max
    from {{ ref('gold_weather_forecast_by_admin_dong') }}
    group by admin_dong_code, date(forecast_at)
),

commerce as (
    select
        admin_dong_code,
        admin_dong,
        gu_code,
        gu,
        business_count,
        business_open_count,
        business_closed_count,
        dataset_count,
        geocoded_count,
        latest_collected_at
    from {{ source('commerce_gold', 'gold_license_dong_summary') }}
)

select
    concat(weather.admin_dong_code, '|', cast(weather.forecast_date as varchar)) as product_row_id,
    weather.admin_dong_code,
    weather.forecast_date,
    weather.admin_dong,
    weather.gu_code,
    weather.gu,
    weather.temp_min_c,
    weather.temp_max_c,
    weather.temp_avg_c,
    weather.precip_prob_max_pct,
    weather.humidity_avg_pct,
    weather.wind_avg_ms,
    weather.wind_max_ms,
    weather.precip_hours,
    weather.snow_hours,
    weather.forecast_hours,
    weather_lineage.weather_issued_at_min,
    weather_lineage.weather_issued_at_max,
    weather_lineage.weather_collected_at_max,
    weather_lineage.weather_published_at_max,
    commerce.admin_dong_code is not null as commerce_observation_present,
    commerce.business_count,
    commerce.business_open_count,
    commerce.business_closed_count,
    commerce.dataset_count,
    commerce.geocoded_count,
    commerce.latest_collected_at as commerce_latest_collected_at,
    weather.weather_daily_product_row_id
from weather
left join weather_lineage
    on weather.admin_dong_code = weather_lineage.admin_dong_code
   and weather.forecast_date = weather_lineage.forecast_date
left join commerce
    on weather.admin_dong_code = commerce.admin_dong_code
   and date(commerce.latest_collected_at) <= weather.forecast_date
