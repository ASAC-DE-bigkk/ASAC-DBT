-- gold_transit_x_weather_dong_hourly — 날씨 조건부 교통 상태 (#289, G6, × weather).
--
-- 한 행 = (admin_dong_code, hour_at)의 교통 지표 + 그 동·시각의 기상청 단기예보.
--   grain: (admin_dong_code, hour_at). 두 용도를 한 grain 으로 담는다:
--     과거 시각 → 교통 실측 + 당시 예보(패턴 학습: "비 올 때 주차 +N%p")
--     미래 시각 → 예보만(교통 컬럼 null, 전망 카드: "내일 15시 비 → 혼잡 상향")
--
-- ── 교통 축: 아카이브 롤업 + 버스 tier1 한정(원칙 ②, #440) ─────────────
--   gold_transit_dong_15min 을 시간으로 롤업. 이 모델은 "비 오는 시간대 vs 아닌 시간대"
--   를 비교하는 용도라 버스는 *_t1 만 소비 — tier2 는 07·13·19시에만 관측돼 시간대
--   구성 편향이 섞인다. 관측수 가중 평균으로 15분 버킷을 접는다(단순 평균은 관측이
--   적은 버킷을 과대대표).
--
-- ── 날씨 축: long → 피벗, 최신 발표분(citydata 선례 재사용) ─────────────
--   silver_weather_forecast_by_admin_dong 은 (동,예보시각,카테고리) long 포맷이고
--   발표(issued_at)가 갱신되므로 max_by(fcst_value_num, issued_at) 로 최신 발표 값을
--   피벗한다(citydata gold_citydata_ppltn_x_weather_hourly 와 동일 관례).
--   TMP 기온·POP 강수확률·PCP 강수량(mm — 원천 '강수없음'은 null, PTY=0 과 함께 해석)·
--   SKY 하늘(1맑음/3구름많음/4흐림)·PTY 강수형태(0없음/1비/2비눈/3눈/4소나기).
--
-- ── 증분(incremental merge) ─────────────────────────────────────────────
--   unique_key=(admin_dong_code, hour_at). 임계 = 교통 프런티어(max hour_at where
--   교통 실측 존재) - 3h. 미래(예보) 행은 항상 임계 이후라 매 런 재계산돼 최신 발표로
--   갱신되고, 임계 이전 과거 행은 '그 시각까지의 최신 발표'가 동결된다 — weather 원천의
--   보존 정책과 무관하게 과거 예보-교통 쌍이 여기 남는다(아카이브 겸용, full_refresh
--   가드도 그래서 건다). 프런티어 산출을 {{ this }} 의 교통 컬럼으로 잡는 이유:
--   max(hour_at) 자체는 미래(예보) 행이라 임계로 쓰면 과거 재계산 창이 사라진다.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['admin_dong_code', 'hour_at'],
    full_refresh=false,
) }}

{%- set threshold %}
{% if is_incremental() %}
(
    select coalesce(max(hour_at), timestamp '1970-01-01') - interval '3' hour
    from {{ this }}
    where bus_obs_cnt_t1 is not null
       or subway_arrival_cnt is not null
       or parking_lot_cnt is not null
)
{% else %}
timestamp '1970-01-01'
{% endif %}
{%- endset %}

with transit_hour as (
    select
        admin_dong_code,
        date_trunc('hour', bucket_at) as hour_at,
        -- 버스 tier1 한정, 관측수 가중.
        sum(bus_obs_cnt_t1) as bus_obs_cnt_t1,
        case when sum(case when bus_congestion_avg_t1 is not null then bus_obs_cnt_t1 end) > 0
             then sum(bus_congestion_avg_t1 * bus_obs_cnt_t1)
                  / sum(case when bus_congestion_avg_t1 is not null then bus_obs_cnt_t1 end)
        end as bus_congestion_avg_t1,
        case when sum(case when bus_full_ratio_t1 is not null then bus_obs_cnt_t1 end) > 0
             then sum(bus_full_ratio_t1 * bus_obs_cnt_t1)
                  / sum(case when bus_full_ratio_t1 is not null then bus_obs_cnt_t1 end)
        end as bus_full_ratio_t1,
        -- 지하철·주차(수집 주기 균일 — 버킷 단순 평균).
        sum(subway_arrival_cnt) as subway_arrival_cnt,
        avg(subway_wait_avg_s) as subway_wait_avg_s,
        max(parking_lot_cnt) as parking_lot_cnt,
        avg(parking_occupancy_avg) as parking_occupancy_avg,
        max(parking_full_lot_cnt) as parking_full_lot_cnt
    from {{ ref('gold_transit_dong_15min') }}
    where bucket_at >= {{ threshold }}
    group by 1, 2
),

weather_hour as (
    select
        admin_dong_code,
        date_trunc('hour', forecast_at) as hour_at,
        max_by(fcst_value_num, issued_at) filter (where category = 'TMP') as temp_c,
        max_by(fcst_value_num, issued_at) filter (where category = 'POP') as precip_prob,
        max_by(fcst_value_num, issued_at) filter (where category = 'PCP') as precip_mm,
        max_by(fcst_value_num, issued_at) filter (where category = 'SKY') as sky_code,
        max_by(fcst_value_num, issued_at) filter (where category = 'PTY') as precip_type,
        max(issued_at) as weather_issued_at
    from {{ source('weather', 'silver_weather_forecast_by_admin_dong') }}
    where admin_dong_code is not null
      and category in ('TMP', 'POP', 'PCP', 'SKY', 'PTY')
      and forecast_at >= {{ threshold }}
    group by 1, 2
),

grain as (
    select admin_dong_code, hour_at from transit_hour
    union
    select admin_dong_code, hour_at from weather_hour
)

select
    g.admin_dong_code,
    g.hour_at,
    -- 교통(과거 실측 — 미래 행은 null)
    t.bus_obs_cnt_t1,
    t.bus_congestion_avg_t1,
    t.bus_full_ratio_t1,
    t.subway_arrival_cnt,
    t.subway_wait_avg_s,
    t.parking_lot_cnt,
    t.parking_occupancy_avg,
    t.parking_full_lot_cnt,
    -- 날씨(그 시각 대상 최신 발표 예보)
    w.temp_c,
    w.precip_prob,
    w.precip_mm,
    w.sky_code,
    w.precip_type,
    (w.precip_type is not null and w.precip_type > 0) as is_precip,
    w.weather_issued_at
from grain g
left join transit_hour t
    on g.admin_dong_code = t.admin_dong_code and g.hour_at = t.hour_at
left join weather_hour w
    on g.admin_dong_code = w.admin_dong_code and g.hour_at = w.hour_at
