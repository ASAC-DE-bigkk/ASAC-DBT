-- missing_context is covered by the paired anchor preservation test; this file isolates duplicate grain rows.
with grain as (
    select admin_dong_code, hour_at, count(*) as row_count
    from {{ ref('gold_weather_x_transit_hourly') }}
    group by admin_dong_code, hour_at
)

select *
from grain
where row_count > 1
