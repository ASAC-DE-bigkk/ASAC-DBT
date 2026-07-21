-- depends_on: {{ ref('gold_weather_current_wide_by_admin_dong') }}
-- depends_on: {{ ref('asac_axes', 'dim_admin_dong') }}

with canonical_counts as (
    select
        cast(admin_dong_code as varchar) as admin_dong_code,
        count(distinct cast(admin_dong_code as varchar)) as canonical_code_count
    from {{ ref('asac_axes', 'dim_admin_dong') }}
    where admin_dong_code is not null
    group by cast(admin_dong_code as varchar)
)

select
    gold.product_row_id,
    gold.admin_dong_code,
    coalesce(canonical.canonical_code_count, 0) as canonical_code_count
from {{ ref('gold_weather_current_wide_by_admin_dong') }} as gold
left join canonical_counts as canonical
    on gold.admin_dong_code = canonical.admin_dong_code
where coalesce(canonical.canonical_code_count, 0) <> 1
