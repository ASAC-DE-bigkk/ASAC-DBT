-- depends_on: {{ ref('gold_weather_current_wide_by_admin_dong') }}
-- depends_on: {{ ref('asac_axes', 'dim_admin_dong') }}

with canonical_ranked as (
    select
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(admin_dong as varchar) as admin_dong,
        cast(gu_code as varchar) as gu_code,
        cast(gu as varchar) as gu,
        row_number() over (
            partition by cast(admin_dong_code as varchar)
            order by try_cast(revision_date as date) desc nulls last
        ) as canonical_row_num
    from {{ ref('asac_axes', 'dim_admin_dong') }}
    where admin_dong_code is not null
),

canonical as (
    select admin_dong_code, admin_dong, gu_code, gu
    from canonical_ranked
    where canonical_row_num = 1
)

select
    gold.product_row_id,
    gold.admin_dong_code,
    gold.admin_dong as actual_admin_dong,
    canonical.admin_dong as expected_admin_dong,
    gold.gu_code as actual_gu_code,
    canonical.gu_code as expected_gu_code,
    gold.gu as actual_gu,
    canonical.gu as expected_gu
from {{ ref('gold_weather_current_wide_by_admin_dong') }} as gold
left join canonical
    on gold.admin_dong_code = canonical.admin_dong_code
where canonical.admin_dong_code is null
   or gold.admin_dong is distinct from canonical.admin_dong
   or gold.gu_code is distinct from canonical.gu_code
   or gold.gu is distinct from canonical.gu
