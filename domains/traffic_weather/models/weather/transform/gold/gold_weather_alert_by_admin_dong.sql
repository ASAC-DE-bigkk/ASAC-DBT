-- W-A4 mart: 동×예보시각 기상 경보 후보 플래그. W-A2 wide 소비.
-- ⚠️ 예보값 근사 = "경보 후보"이며 공식 기상특보가 아님(임계 기준 공식 대조 필요).
--   heat≥33/경보≥35, cold≤-12, heavy_rain(비류 & PCP≥15mm), snow(SNO≥1cm), wind(WSD≥14).

with w as (
    select
        admin_dong_code, admin_dong, gu_code, gu, forecast_at, issued_at,
        temp_c, wind_ms, precip_prob_pct, pty_code, pcp_mm, pcp_upper_mm, sno_cm
    from {{ ref('gold_weather_forecast_wide_by_admin_dong') }}
),

flagged as (
    select
        w.*,
        (temp_c >= 33) as heat_flag,
        (temp_c >= 35) as heat_warning_flag,
        (temp_c <= -12) as cold_flag,
        (pty_code in ('1', '4', '5') and coalesce(pcp_mm, pcp_upper_mm, 0) >= 15) as heavy_rain_flag,
        (coalesce(sno_cm, 0) >= 1) as snow_flag,
        (wind_ms >= 14) as wind_flag
    from w
)

select
    concat(admin_dong_code, '|', to_iso8601(cast(forecast_at as timestamp(6)))) as product_row_id,
    admin_dong_code,
    forecast_at,
    admin_dong,
    gu_code,
    gu,
    issued_at,
    temp_c,
    wind_ms,
    precip_prob_pct,
    pcp_mm,
    sno_cm,
    pty_code,
    heat_flag,
    heat_warning_flag,
    cold_flag,
    heavy_rain_flag,
    snow_flag,
    wind_flag,
    (heat_flag or cold_flag or heavy_rain_flag or snow_flag or wind_flag) as any_alert,
    array_join(filter(array[
        if(heat_warning_flag, '폭염경보', if(heat_flag, '폭염주의', cast(null as varchar))),
        if(cold_flag, '한파', cast(null as varchar)),
        if(heavy_rain_flag, '호우', cast(null as varchar)),
        if(snow_flag, '대설', cast(null as varchar)),
        if(wind_flag, '강풍', cast(null as varchar))
    ], v -> v is not null), ', ') as alert_labels
from flagged
