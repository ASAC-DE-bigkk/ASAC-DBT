select
    place_id,
    issued_at,
    forecast_at,
    category,
    count(*) as row_count
from {{ ref('silver_weather_forecast_by_admin_dong') }}
group by place_id, issued_at, forecast_at, category
having count(*) > 1
