-- depends_on: {{ ref('gold_weather_forecast_by_admin_dong') }}

select
    admin_dong_code,
    forecast_at,
    category,
    count(*) as row_count
from {{ ref('gold_weather_forecast_by_admin_dong') }}
group by admin_dong_code, forecast_at, category
having count(*) > 1
