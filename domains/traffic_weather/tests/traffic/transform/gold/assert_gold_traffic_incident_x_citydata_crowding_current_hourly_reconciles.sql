{{ config(tags=['traffic_gold_gate']) }}

with traffic as (
    select
        product_row_id,
        admin_dong_code,
        hour_at,
        incident_count,
        has_incident,
        quality_state
    from {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}
),

gold as (
    select
        product_row_id,
        admin_dong_code,
        hour_at,
        incident_count,
        has_incident,
        quality_state
    from {{ ref('gold_traffic_incident_x_citydata_crowding_current_hourly') }}
),

joined as (
    select
        coalesce(traffic.product_row_id, gold.product_row_id) as product_row_id,
        traffic.product_row_id is null as missing_traffic_row,
        gold.product_row_id is null as missing_gold_row,
        traffic.admin_dong_code is distinct from gold.admin_dong_code
            as admin_dong_code_changed,
        traffic.hour_at is distinct from gold.hour_at as hour_at_changed,
        traffic.incident_count is distinct from gold.incident_count
            as incident_count_changed,
        traffic.has_incident is distinct from gold.has_incident as has_incident_changed,
        traffic.quality_state is distinct from gold.quality_state as quality_state_changed
    from traffic
    full outer join gold
        on traffic.product_row_id = gold.product_row_id
)

select *
from joined
where missing_traffic_row
   or missing_gold_row
   or admin_dong_code_changed
   or hour_at_changed
   or incident_count_changed
   or has_incident_changed
   or quality_state_changed
