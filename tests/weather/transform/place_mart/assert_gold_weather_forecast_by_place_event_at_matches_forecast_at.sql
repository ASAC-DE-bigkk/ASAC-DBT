select *
from {{ ref('gold_weather_forecast_by_place') }}
where event_at is null
   or event_at <> forecast_at
