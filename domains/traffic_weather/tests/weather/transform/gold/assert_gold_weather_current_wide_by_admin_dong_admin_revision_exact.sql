-- depends_on: {{ ref('gold_weather_current_wide_by_admin_dong') }}
-- depends_on: {{ ref('asac_axes', 'dim_admin_dong') }}

with canonical_ranked as (
    select
        cast(admin_dong_code as varchar) as admin_dong_code,
        try_cast(revision_date as date) as admin_dong_revision_date,
        row_number() over (
            partition by cast(admin_dong_code as varchar)
            order by try_cast(revision_date as date) desc nulls last
        ) as canonical_row_num
    from {{ ref('asac_axes', 'dim_admin_dong') }}
    where admin_dong_code is not null
),

canonical as (
    select admin_dong_code, admin_dong_revision_date
    from canonical_ranked
    where canonical_row_num = 1
)

select
    gold.product_row_id,
    gold.admin_dong_code,
    gold.admin_dong_revision_date as actual_revision_date,
    canonical.admin_dong_revision_date as expected_revision_date
from {{ ref('gold_weather_current_wide_by_admin_dong') }} as gold
left join canonical
    on gold.admin_dong_code = canonical.admin_dong_code
where canonical.admin_dong_code is null
   or gold.admin_dong_revision_date is distinct from canonical.admin_dong_revision_date
