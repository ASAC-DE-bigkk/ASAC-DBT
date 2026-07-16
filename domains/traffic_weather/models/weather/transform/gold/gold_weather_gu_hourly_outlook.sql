-- Serving Gold: gu × forecast-hour weather outlook aggregated from canonical dong rows.
-- Grain: (gu_code, forecast_at).  Coverage is the observed source-dong count,
-- not a claim of complete district coverage.

{{ config(materialized='table') }}

with wide as (
    select *
    from {{ ref('gold_weather_forecast_wide_by_admin_dong') }}
)

select
    concat(gu_code, '|', to_iso8601(cast(forecast_at as timestamp(6)))) as product_row_id,
    gu_code,
    max(gu) as gu,
    forecast_at,
    count(distinct admin_dong_code) as source_admin_dong_count,
    min(issued_at) as forecast_issued_at_min,
    max(issued_at) as forecast_issued_at_max,
    round(avg(temp_c), 1) as temp_avg_c,
    min(temp_c) as temp_min_c,
    max(temp_c) as temp_max_c,
    round(avg(humidity_pct), 1) as humidity_avg_pct,
    max(wind_ms) as wind_max_ms,
    max(precip_prob_pct) as precip_prob_max_pct,
    avg(case when is_precipitating then 1.0 else 0.0 end) as precipitation_dong_ratio,
    max(pcp_mm) as pcp_max_mm,
    max(sno_cm) as sno_max_cm,
    max(published_at) as weather_published_at_max
from wide
group by gu_code, forecast_at
