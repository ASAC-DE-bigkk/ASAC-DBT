select product_row_id
from {{ ref('gold_traffic_incident_x_citydata_crowding_current_hourly') }}
where citydata_crowding_snapshot_id is distinct from
      cast({{ traffic_citydata_crowding_snapshot_id() }} as bigint)
