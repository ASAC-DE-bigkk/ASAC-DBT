select *
from {{ ref('gold_traffic_incident_x_weather_current_hourly') }}
where weather_category_coverage_count is null
  and (
      weather_latest_issued_at is not null
      or weather_latest_collected_at is not null
      or weather_latest_published_at is not null
      or tmp_value_num is not null
      or pop_value_num is not null
      or reh_value_num is not null
      or wsd_value_num is not null
      or sky_qualitative_code is not null
      or pty_qualitative_code is not null
      or is_precipitating is not null
  )
