-- W-A6 mart: 동×일 강수 특화 프로파일. 정본 long gold 소비, 값 의미계층 활용.
--   PTY 코드: 1비·4소나기·5빗방울 / 3눈·7눈날림 / 2비눈·6빗방울눈날림.

with src as (
    select
        admin_dong_code, admin_dong, gu_code, gu,
        forecast_at, category, qualitative_code, value_num
    from {{ ref('gold_weather_forecast_by_admin_dong') }}
),

daily as (
    select
        admin_dong_code,
        date(forecast_at) as forecast_date,
        max(admin_dong) as admin_dong,
        max(gu_code) as gu_code,
        max(gu) as gu,
        max(value_num) filter (where category = 'POP') as precip_prob_max_pct,
        round(avg(value_num) filter (where category = 'POP'), 1) as precip_prob_avg_pct,
        count(distinct forecast_at) filter (
            where category = 'PTY' and qualitative_code is not null and qualitative_code <> '0'
        ) as precip_hours,
        count(distinct forecast_at) filter (
            where category = 'PTY' and qualitative_code in ('1', '4', '5')
        ) as rain_hours,
        count(distinct forecast_at) filter (
            where category = 'PTY' and qualitative_code in ('3', '7')
        ) as snow_hours,
        count(distinct forecast_at) filter (
            where category = 'PTY' and qualitative_code in ('2', '6')
        ) as sleet_hours,
        max(value_num) filter (where category = 'PCP') as pcp_max_mm,
        round(sum(value_num) filter (where category = 'PCP'), 1) as pcp_sum_mm,
        max(value_num) filter (where category = 'SNO') as sno_max_cm
    from src
    group by admin_dong_code, date(forecast_at)
)

select
    concat(admin_dong_code, '|', cast(forecast_date as varchar)) as product_row_id,
    admin_dong_code,
    forecast_date,
    admin_dong,
    gu_code,
    gu,
    precip_prob_max_pct,
    precip_prob_avg_pct,
    precip_hours,
    rain_hours,
    snow_hours,
    sleet_hours,
    pcp_max_mm,
    pcp_sum_mm,
    sno_max_cm
from daily
