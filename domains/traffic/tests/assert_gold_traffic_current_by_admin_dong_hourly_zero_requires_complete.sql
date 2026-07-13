-- depends_on: {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}

select
    product_row_id,
    admin_dong_code,
    hour_at,
    quality_state,
    snapshot_as_of_at,
    incident_count,
    has_incident
from {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}
where quality_state is null
   or quality_state not in (
       'complete',
       'complete_zero',
       'missing',
       'partial',
       'api_failure',
       'current_mismatch',
       'spatial_mapping_incomplete'
   )
   or incident_count < 0
   or (
       quality_state in ('complete', 'complete_zero')
       and (
           snapshot_as_of_at is null
           or incident_count is null
           or has_incident is null
           or has_incident is distinct from (incident_count > 0)
       )
   )
   or (
       quality_state not in ('complete', 'complete_zero')
       and (
           snapshot_as_of_at is not null
           or incident_count is not null
           or has_incident is not null
       )
   )
   or (quality_state = 'complete_zero' and incident_count <> 0)
