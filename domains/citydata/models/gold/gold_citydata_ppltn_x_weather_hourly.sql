-- gold: 인구혼잡 × 날씨(예보) (크로스도메인). grain = (time_bucket=시간, admin_dong_code).
--
-- 우리 인구를 행정동×시간으로 롤업하고, 그 시간·동의 기상청 단기예보(weather)를 붙인다.
-- 답: 비/추위/흐림 예보 시간대에 붐빔이 어떻게 변하나.
--
-- weather 는 long 포맷(category별 1행)이라 (동, 예보시각)으로 피벗 — 최신 발표분(issued_at)
-- 값 사용. 예보값이므로 관측이 아닌 '예보된 날씨 vs 실제 붐빔'. 크로스도메인 source()
-- (schema=weather). 조인축 admin_dong_code(라이브 B). 커버리지=우리 핫플 동 한정.

-- view: R2 delete+insert 의 비원자성으로 incremental 시 시간별 재삽입 중복이 재발해
-- (unique_grain 5분마다 FAIL→알림) view 로 전환. 물리 write 없어 중복 불가·항상 라이브.
-- 시간 grain 조인이라 조회 시 재계산(~1-2s) 감당 가능.
{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", "seoul_citydata"),
    materialized='view',
) }}

with ppltn_dong as (
    select
        date_trunc('hour', event_at) as time_bucket,
        admin_dong_code,
        max(gu_code) as gu_code,
        avg((area_ppltn_min + area_ppltn_max) / 2.0) as ppltn_avg,
        max((area_ppltn_min + area_ppltn_max) / 2.0) as ppltn_peak,
        count(distinct area_cd) as hotspot_count
    from {{ ref('silver_citydata_ppltn') }}
    where admin_dong_code is not null
    {% if is_incremental() %}
      and event_at >= (
        select coalesce(max(time_bucket), timestamp '1970-01-01') - interval '2' hour from {{ this }}
    )
    {% endif %}
    group by 1, 2
),

-- 기상청 단기예보 피벗: (동, 예보시각)별 최신 발표(issued_at) 값. TMP기온·POP강수확률·
-- REH습도·WSD풍속·SKY하늘(1맑음/3구름많음/4흐림)·PTY강수형태(0없음/1비/2비눈/3눈/4소나기).
weather_hour as (
    select
        admin_dong_code,
        date_trunc('hour', forecast_at) as fh,
        max_by(fcst_value_num, issued_at) filter (where category = 'TMP') as temp_c,
        max_by(fcst_value_num, issued_at) filter (where category = 'POP') as precip_prob,
        max_by(fcst_value_num, issued_at) filter (where category = 'REH') as humidity,
        max_by(fcst_value_num, issued_at) filter (where category = 'WSD') as wind_ms,
        max_by(fcst_value_num, issued_at) filter (where category = 'SKY') as sky_code,
        max_by(fcst_value_num, issued_at) filter (where category = 'PTY') as precip_type
    from {{ source('weather', 'silver_weather_forecast_by_admin_dong') }}
    where admin_dong_code is not null
    group by 1, 2
)

select
    p.time_bucket,
    p.admin_dong_code,
    m.admin_dong,
    p.gu_code,
    m.gu,
    p.hotspot_count,
    round(p.ppltn_avg, 1) as ppltn_avg,
    round(p.ppltn_peak, 1) as ppltn_peak,
    w.temp_c,
    w.precip_prob,
    w.humidity,
    w.wind_ms,
    w.sky_code,
    w.precip_type,
    (w.precip_type is not null and w.precip_type > 0) as is_raining
from ppltn_dong p
left join weather_hour w
    on w.admin_dong_code = p.admin_dong_code and w.fh = p.time_bucket
left join {{ ref('asac_axes', 'dim_admin_dong') }} m
    on p.admin_dong_code = m.admin_dong_code
