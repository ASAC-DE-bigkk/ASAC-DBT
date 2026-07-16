select
    product_row_id,
    issued_at,
    forecast_date,
    expected_cell_count,
    observed_cell_count,
    missing_cell_count,
    issue_cycle_coverage_ratio
from {{ ref('gold_weather_forecast_issue_cycle_coverage_daily') }}
where observed_cell_count > expected_cell_count
   or missing_cell_count < 0
   or expected_cell_count < 0
   or (issue_cycle_coverage_ratio is not null and issue_cycle_coverage_ratio < 0)
   or (issue_cycle_coverage_ratio is not null and issue_cycle_coverage_ratio > 1)
   or (expected_cell_count = 0 and issue_cycle_coverage_ratio is not null)
   or (expected_cell_count > 0 and issue_cycle_coverage_ratio is null)
