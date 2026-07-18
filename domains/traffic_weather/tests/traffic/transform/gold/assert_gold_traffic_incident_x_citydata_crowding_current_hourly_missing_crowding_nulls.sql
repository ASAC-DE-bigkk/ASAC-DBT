{{ config(tags=['traffic_gold_gate']) }}

select *
from {{ ref('gold_traffic_incident_x_citydata_crowding_current_hourly') }}
where monitored_place_count is null
  and (
      avg_place_avg_ppltn is not null
      or peak_place_avg_ppltn is not null
      or crowding_latest_observed_at is not null
      or crowding_latest_collected_at is not null
      or crowding_observed is distinct from false
  )
