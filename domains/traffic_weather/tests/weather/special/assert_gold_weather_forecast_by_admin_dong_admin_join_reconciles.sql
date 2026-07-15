-- depends_on: {{ ref('gold_weather_forecast_by_admin_dong') }}

{% set canonical_contract = weather_w2_canonical_contract() %}

with canonical_counts as (
    select
        cast(admin_dong_code as varchar) as admin_dong_code,
        count(*) as canonical_row_count
    from {{ ref('asac_axes', 'dim_admin_dong') }}
    where cast(revision_date as date) = date '{{ canonical_contract['revision_date'] }}'
    group by cast(admin_dong_code as varchar)
)

select
    gold.product_row_id,
    gold.admin_dong_code,
    coalesce(canonical.canonical_row_count, 0) as canonical_row_count
from {{ ref('gold_weather_forecast_by_admin_dong') }} as gold
left join canonical_counts as canonical
    on gold.admin_dong_code = canonical.admin_dong_code
where coalesce(canonical.canonical_row_count, 0) <> 1
