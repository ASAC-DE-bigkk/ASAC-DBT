-- depends_on: {{ ref('silver_seoul_traffic_incident') }}
select *
from {{ ref('silver_seoul_traffic_incident') }}
where source_location_quality = 'source_coordinate_available'
  and (longitude is null or latitude is null)
