-- depends_on: {{ ref('gold_weather_forecast_by_admin_dong') }}

{% set canonical_contract = weather_w2_canonical_contract() %}

select
    gold.product_row_id,
    gold.admin_dong_code,
    gold.admin_dong as actual_admin_dong,
    canonical.admin_dong as expected_admin_dong,
    gold.gu_code as actual_gu_code,
    canonical.gu_code as expected_gu_code,
    gold.gu as actual_gu,
    canonical.gu as expected_gu
from {{ ref('gold_weather_forecast_by_admin_dong') }} as gold
left join {{ asac_axes.pinned_dim_admin_dong() }} as canonical
    on gold.admin_dong_code = cast(canonical.admin_dong_code as varchar)
   and cast(canonical.revision_date as date) = date '{{ canonical_contract['revision_date'] }}'
where canonical.admin_dong_code is null
   or gold.admin_dong is distinct from cast(canonical.admin_dong as varchar)
   or gold.gu_code is distinct from cast(canonical.gu_code as varchar)
   or gold.gu is distinct from cast(canonical.gu as varchar)
