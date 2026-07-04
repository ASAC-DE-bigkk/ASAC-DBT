select
    place_id,
    forecast_at,
    category,
    count(*) as row_count
from {{ ref('gold_weather_forecast_by_place') }}
group by place_id, forecast_at, category
having count(*) > 1
