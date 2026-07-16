-- Serving Gold: large adjacent-hour temperature forecast changes by mapped place.
-- Grain: (place_id, forecast_at); the threshold is a descriptive alerting
-- heuristic and must not be read as an official weather warning.

{{ config(materialized='table') }}

with ordered as (
    select
        hourly.*,
        lag(temp_c) over (
            partition by place_id
            order by forecast_at
        ) as previous_temp_c,
        lag(forecast_at) over (
            partition by place_id
            order by forecast_at
        ) as previous_forecast_at
    from {{ ref('gold_weather_place_hourly_outlook') }} as hourly
),

changed as (
    select
        *,
        temp_c - previous_temp_c as temp_change_c
    from ordered
    where temp_c is not null
      and previous_temp_c is not null
      and abs(temp_c - previous_temp_c) >= 3
)

select
    concat(place_id, '|', to_iso8601(cast(forecast_at as timestamp(6)))) as product_row_id,
    place_id,
    place_name,
    admin_dong_code,
    admin_dong,
    gu_code,
    gu,
    previous_forecast_at,
    forecast_at,
    previous_temp_c,
    temp_c,
    temp_change_c,
    case
        when temp_change_c > 0 then 'warming'
        else 'cooling'
    end as temperature_change_direction,
    forecast_issued_at_min,
    forecast_issued_at_max,
    forecast_collected_at_max
from changed
