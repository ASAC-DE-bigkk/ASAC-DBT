{{ config(tags=['traffic_gold_gate']) }}
-- depends_on: {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}

select
    admin_dong_code,
    hour_at,
    product_row_id,
    concat(
        admin_dong_code,
        '|',
        to_iso8601(cast(hour_at as timestamp(6)))
    ) as expected_product_row_id
from {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}
where product_row_id is distinct from concat(
    admin_dong_code,
    '|',
    to_iso8601(cast(hour_at as timestamp(6)))
)
