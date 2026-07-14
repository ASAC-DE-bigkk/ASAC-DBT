-- depends_on: {{ ref('silver_seoul_traffic_incident') }}
with coverage as (
    select
        count(*) as coordinate_row_count,
        count(admin_dong_code) as mapped_row_count
    from {{ ref('silver_seoul_traffic_incident') }}
    where source_location_quality = 'source_coordinate_available'
)

select *
from coverage
where coordinate_row_count > 0
  and mapped_row_count * 1.0 / coordinate_row_count < 0.80
