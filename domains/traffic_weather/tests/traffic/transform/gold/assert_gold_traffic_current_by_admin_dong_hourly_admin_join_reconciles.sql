{{ config(tags=['traffic_gold_gate']) }}
-- depends_on: {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}
-- depends_on: {{ ref('asac_axes', 'seoul_admin_dong_crosswalk') }}
-- depends_on: {{ source('axes_bronze', 'admin_dong_master') }}

with canonical_counts as (
    select
        cast(admin_dong_code as varchar) as admin_dong_code,
        count(*) as canonical_row_count
    from {{ asac_axes.pinned_dim_admin_dong() }}
    group by cast(admin_dong_code as varchar)
)

select
    gold.product_row_id,
    gold.admin_dong_code,
    coalesce(canonical.canonical_row_count, 0) as canonical_row_count
from {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }} as gold
left join canonical_counts as canonical
    on gold.admin_dong_code = canonical.admin_dong_code
where coalesce(canonical.canonical_row_count, 0) <> 1
