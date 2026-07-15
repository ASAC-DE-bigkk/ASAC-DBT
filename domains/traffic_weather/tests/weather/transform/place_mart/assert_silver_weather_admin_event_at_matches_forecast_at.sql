select *
from {{ ref('silver_weather_forecast_by_admin_dong') }}
where event_at is null
   or event_at <> forecast_at
