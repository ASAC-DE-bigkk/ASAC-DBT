{{ config(tags=['traffic_gold_gate']) }}
-- depends_on: {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}
-- depends_on: {{ ref('asac_axes', 'seoul_admin_dong_crosswalk') }}
-- depends_on: {{ source('axes_bronze', 'admin_dong_master') }}

select
    gold.product_row_id,
    gold.admin_dong_code,
    gold.admin_dong as actual_admin_dong,
    cast(canonical.admin_dong as varchar) as expected_admin_dong,
    gold.gu_code as actual_gu_code,
    cast(canonical.gu_code as varchar) as expected_gu_code,
    gold.gu as actual_gu,
    cast(canonical.gu as varchar) as expected_gu,
    gold.admin_dong_revision_date as actual_revision_date,
    cast(canonical.revision_date as date) as expected_revision_date
from {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }} as gold
left join {{ asac_axes.pinned_dim_admin_dong() }} as canonical
    on gold.admin_dong_code = cast(canonical.admin_dong_code as varchar)
where canonical.admin_dong_code is null
   or gold.admin_dong is distinct from cast(canonical.admin_dong as varchar)
   or gold.gu_code is distinct from cast(canonical.gu_code as varchar)
   or gold.gu is distinct from cast(canonical.gu as varchar)
   or gold.admin_dong_revision_date is distinct from cast(canonical.revision_date as date)
