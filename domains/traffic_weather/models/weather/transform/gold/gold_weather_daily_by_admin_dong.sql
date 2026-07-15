-- W-A3 mart: 동×일 KMA 예보 일 롤업. 정본 gold(LONG)에서 category별 집계.
-- materialized=table·schema=weather·tag=ask_seoul_weather_transform_gold 은 dbt_project.yml 상속.

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
        min(value_num) filter (where category = 'TMP') as temp_min_c,
        max(value_num) filter (where category = 'TMP') as temp_max_c,
        avg(value_num) filter (where category = 'TMP') as temp_avg_c,
        max(value_num) filter (where category = 'TMN') as tmn_c,
        max(value_num) filter (where category = 'TMX') as tmx_c,
        max(value_num) filter (where category = 'POP') as precip_prob_max_pct,
        avg(value_num) filter (where category = 'REH') as humidity_avg_pct,
        avg(value_num) filter (where category = 'WSD') as wind_avg_ms,
        max(value_num) filter (where category = 'WSD') as wind_max_ms,
        count(distinct forecast_at) filter (
            where category = 'PTY' and qualitative_code is not null and qualitative_code <> '0'
        ) as precip_hours,
        count(distinct forecast_at) filter (
            where category = 'PTY' and qualitative_code in ('3', '7')
        ) as snow_hours,
        count(distinct forecast_at) filter (where category = 'TMP') as forecast_hours
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
    temp_min_c,
    temp_max_c,
    round(temp_avg_c, 1) as temp_avg_c,
    tmn_c,
    tmx_c,
    precip_prob_max_pct,
    round(humidity_avg_pct, 1) as humidity_avg_pct,
    round(wind_avg_ms, 1) as wind_avg_ms,
    wind_max_ms,
    precip_hours,
    snow_hours,
    forecast_hours
from daily
