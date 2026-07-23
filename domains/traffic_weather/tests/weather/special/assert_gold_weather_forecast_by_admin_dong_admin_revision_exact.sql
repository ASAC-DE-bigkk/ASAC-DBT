-- depends_on: {{ ref('gold_weather_forecast_by_admin_dong') }}

{% set canonical_contract = weather_w2_canonical_contract() %}

select
    gold.product_row_id,
    gold.admin_dong_code,
    gold.admin_dong_revision_date as actual_revision_date,
    cast(canonical.revision_date as date) as expected_revision_date
from {{ ref('gold_weather_forecast_by_admin_dong') }} as gold
left join {{ asac_axes.pinned_dim_admin_dong() }} as canonical
    on gold.admin_dong_code = cast(canonical.admin_dong_code as varchar)
   and cast(canonical.revision_date as date) = date '{{ canonical_contract['revision_date'] }}'
where canonical.admin_dong_code is null
   or gold.admin_dong_revision_date is distinct from cast(canonical.revision_date as date)
