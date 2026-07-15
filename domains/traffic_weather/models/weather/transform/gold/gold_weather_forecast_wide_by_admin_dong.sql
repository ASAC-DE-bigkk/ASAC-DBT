-- W-A2 mart: 동×예보시각 전 horizon KMA 예보 WIDE. 정본 gold만 소비. current 필터 없음.
-- materialized=table·schema=weather·tag=ask_seoul_weather_transform_gold 은 dbt_project.yml 상속.

{% set published_at_utc = run_started_at.strftime('%Y-%m-%d %H:%M:%S.%f') %}

with src as (
    select
        admin_dong_code, admin_dong, gu_code, gu, admin_dong_revision_date,
        forecast_at, issued_at, category,
        fcst_value_raw, value_representation, value_num,
        value_lower_bound, value_upper_bound, qualitative_code
    from {{ ref('gold_weather_forecast_by_admin_dong') }}
),

pivoted as (
    select
        admin_dong_code,
        forecast_at,
        max(admin_dong) as admin_dong,
        max(gu_code) as gu_code,
        max(gu) as gu,
        max(admin_dong_revision_date) as admin_dong_revision_date,
        max(issued_at) as issued_at,
        {{ weather_wide_pivot() }}
    from src
    group by admin_dong_code, forecast_at
)

select
    concat(admin_dong_code, '|', to_iso8601(cast(forecast_at as timestamp(6)))) as product_row_id,
    admin_dong_code,
    forecast_at,
    admin_dong,
    gu_code,
    gu,
    admin_dong_revision_date,
    issued_at,
    temp_c,
    humidity_pct,
    wind_ms,
    wind_dir_deg,
    precip_prob_pct,
    sky_code,
    {{ weather_sky_label('sky_code') }} as sky_label,
    pty_code,
    {{ weather_pty_label('pty_code') }} as pty_label,
    (pty_code is not null and pty_code <> '0') as is_precipitating,
    pcp_raw,
    pcp_representation,
    pcp_mm,
    pcp_lower_mm,
    pcp_upper_mm,
    sno_raw,
    sno_representation,
    sno_cm,
    date_diff('hour', issued_at, forecast_at) as forecast_lead_hours,
    cast(timestamp '{{ published_at_utc }}' + interval '9' hour as timestamp(6)) as published_at
from pivoted
