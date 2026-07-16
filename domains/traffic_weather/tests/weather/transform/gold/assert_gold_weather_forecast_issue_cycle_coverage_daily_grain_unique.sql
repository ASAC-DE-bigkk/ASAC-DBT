-- missing_context is covered by the paired reconciliation test; this file isolates duplicate grain rows.
with grain as (
    select
        issued_at,
        forecast_date,
        count(*) as row_count
    from {{ ref('gold_weather_forecast_issue_cycle_coverage_daily') }}
    group by issued_at, forecast_date
)

select *
from grain
where row_count > 1
