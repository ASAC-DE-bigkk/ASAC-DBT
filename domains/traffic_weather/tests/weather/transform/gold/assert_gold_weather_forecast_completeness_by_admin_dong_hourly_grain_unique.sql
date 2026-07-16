-- missing_context is covered by the paired reconciliation test; this file isolates duplicate grain rows.
with grain as (
    select
        admin_dong_code,
        forecast_at,
        count(*) as row_count
    from {{ ref('gold_weather_forecast_completeness_by_admin_dong_hourly') }}
    group by admin_dong_code, forecast_at
)

select *
from grain
where row_count > 1
