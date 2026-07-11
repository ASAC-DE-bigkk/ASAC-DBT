select
    source_record_id,
    grs80tm_x,
    grs80tm_y,
    source_coordinate_system,
    source_location_quality
from {{ ref('silver_seoul_traffic_incident') }}
where source_coordinate_system != 'GRS80_TM'
   or source_location_quality not in ('source_coordinate_available', 'source_coordinate_missing')
   or (
       source_location_quality = 'source_coordinate_available'
       and (grs80tm_x is null or grs80tm_y is null)
   )
   or (
       source_location_quality = 'source_coordinate_missing'
       and grs80tm_x is not null
       and grs80tm_y is not null
   )
