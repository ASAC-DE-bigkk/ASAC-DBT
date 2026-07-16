-- Serving Gold: mapped-place daily forecast rollup.
-- Grain: (place_id, forecast_date).  Null source metrics stay null; the hour
-- count tells consumers how much hourly forecast evidence is represented.

{{ config(materialized='table') }}

with hourly as (
    select *
    from {{ ref('gold_weather_place_hourly_outlook') }}
)

select
    concat(place_id, '|', cast(cast(forecast_at as date) as varchar)) as product_row_id,
    place_id,
    max(place_name) as place_name,
    max(alias_names) as alias_names,
    max(admin_dong_code) as admin_dong_code,
    max(admin_dong) as admin_dong,
    max(gu_code) as gu_code,
    max(gu) as gu,
    cast(forecast_at as date) as forecast_date,
    count(*) as forecast_hour_count,
    min(forecast_issued_at_min) as forecast_issued_at_min,
    max(forecast_issued_at_max) as forecast_issued_at_max,
    min(temp_c) as temp_min_c,
    max(temp_c) as temp_max_c,
    round(avg(temp_c), 1) as temp_avg_c,
    max(precip_prob_pct) as precip_prob_max_pct,
    count_if(is_precipitating) as precipitation_hour_count,
    max(wind_ms) as wind_max_ms,
    max(sno_cm) as sno_max_cm,
    max(forecast_collected_at_max) as forecast_collected_at_max
from hourly
group by place_id, cast(forecast_at as date)
