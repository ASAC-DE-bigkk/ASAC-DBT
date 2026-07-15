-- W-A5 mart·D1: 구×현재시각 대표 예보. W-A1(동 current wide) 롤업.
-- 대표값: 수치는 평균/최소/최대, sky는 최댓값(=가장 흐림), 강수는 동 비율.

with d as (
    select
        gu_code, gu, forecast_at,
        temp_c, humidity_pct, wind_ms, precip_prob_pct, sky_code, is_precipitating
    from {{ ref('gold_weather_current_wide_by_admin_dong') }}
)

select
    gu_code as product_row_id,
    gu_code,
    gu,
    max(forecast_at) as forecast_at,
    count(*) as dong_count,
    round(avg(temp_c), 1) as temp_avg_c,
    round(min(temp_c), 1) as temp_min_c,
    round(max(temp_c), 1) as temp_max_c,
    round(avg(humidity_pct), 1) as humidity_avg_pct,
    round(avg(wind_ms), 1) as wind_avg_ms,
    max(precip_prob_pct) as precip_prob_max_pct,
    max(sky_code) as sky_code_cloudiest,
    {{ weather_sky_label('max(sky_code)') }} as sky_label_cloudiest,
    count(*) filter (where is_precipitating) as precipitating_dong_count,
    round(cast(count(*) filter (where is_precipitating) as double) / count(*), 3) as precipitating_dong_ratio
from d
group by gu_code, gu
