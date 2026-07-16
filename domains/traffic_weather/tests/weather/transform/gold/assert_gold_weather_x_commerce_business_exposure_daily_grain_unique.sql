-- missing_context is covered by the paired anchor preservation test; this file isolates duplicate grain rows.
with grain as (
    select admin_dong_code, forecast_date, count(*) as row_count
    from {{ ref('gold_weather_x_commerce_business_exposure_daily') }}
    group by admin_dong_code, forecast_date
)

select *
from grain
where row_count > 1
