-- depends_on: {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}

with keyed as (
    select
        product_row_id,
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(hour_at as timestamp(6)) as hour_at,
        count(*) over (
            partition by admin_dong_code, hour_at
        ) as natural_grain_row_count,
        count(*) over (
            partition by product_row_id
        ) as product_row_id_row_count
    from {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}
)

select *
from keyed
where product_row_id is null
   or admin_dong_code is null
   or hour_at is null
   or natural_grain_row_count <> 1
   or product_row_id_row_count <> 1
