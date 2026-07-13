# Weather Incremental Lookback Design

## Goal

Apply a bounded 30-minute `collected_at` replay window to the existing Weather Grid and admin-dong Silver incremental MERGE models without changing their grains or touching another domain.

## Design

- Reuse `weather_w1_lookback_minutes()` only as the validated numeric setting; do not invoke its W1 isolated-environment guards from legacy operating models.
- In `silver_kma_vilage_fcst` and `silver_weather_forecast_by_admin_dong`, replace the strict `collected_at > max(collected_at)` watermark with inclusive `collected_at >= max(collected_at) - interval '<minutes>' minute`.
- Preserve each model's existing `incremental_strategy='merge'`, `unique_key`, and `on_schema_change='fail'` contracts. The replay window updates matching grains rather than appending duplicate rows.
- Add regression tests that inspect the compiled model source contract for the macro-backed inclusive lookback and unchanged unique keys.
- Correct Weather operating documentation to distinguish the legacy operating models from W1 candidate relations and describe the replay-window limit for arrivals older than 30 minutes.

## Validation

- Python regression tests, dbt parse/compile, and scoped dev `dbt run/test` for both Silver models.
- Re-run the scoped command to confirm the second incremental pass does not create duplicate grains.
- No relation outside the Weather schema is selected or written.
