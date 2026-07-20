-- gold_transit_forecast_card — "내일 이 시간 교통" 예측 카드 (#292, G10, × citydata × weather).
--
-- 한 행 = (area_cd, target_hour_at 미래 시각)의 예상 카드. grain: (area_cd, target_hour_at).
--   사용자 화면: "내일(토) 15시 강남역 일대: 인구 '붐빔' 예상 + 비 예보 → 주차 비추천,
--   지하철 이용". 유일한 순수 '미래' 제품 — 세 원천이 전부 예보/프로파일 성격이라 가능.
--
-- ── 3원 결합 ───────────────────────────────────────────────────────────
--   ① 기대 인구: citydata gold_citydata_ppltn_forecast (area × 주중/주말 × 시).
--   ② 날씨 예보: gold_transit_x_weather_dong_hourly(G6 #289)의 미래 행 재사용 —
--      피벗·최신발표 선별이 이미 끝난 형태라 재계산하지 않는다(핫스팟 동 × 시각).
--   ③ 평시 교통: gold_transit_dong_rhythm(G4 #287)의 (동, dow, hh) 칸 —
--      주차 점유·버스 혼잡(tier1) 기준선 + base_n(표본 신뢰도 승계).
--
-- ── 미래 구간 ──────────────────────────────────────────────────────────
--   target_hour_at > 교통 아카이브 프런티어(max bucket_at) 인 시각만 — 과거는
--   G6(실측+당시예보 아카이브)의 몫이고, 이 카드는 '앞으로'만 답한다.
--   상한은 날씨 예보 가용 범위(단기예보 +3일)가 자연 결정.
--
-- ── 추천 플래그(v1 단순 규칙 — 공식 고도화는 후속) ──────────────────────
--   parking_busy_expected: 평시 점유 >= 0.8 (표본 base_n >= 4 인 칸만 판정).
--   is_precip_expected: 강수형태 예보 > 0.
--   transit_recommended: 둘 중 하나라도 참. 자의성 있는 합성 점수 대신 해석
--   가능한 불리언 3개만 노출 — 문구화는 소비 측(대시보드) 몫.
--
-- ── 재질(table) ────────────────────────────────────────────────────────
--   예보·프로파일이 매 런 갱신되는 순수 파생 스냅샷 — 전체 재생성. 아카이브 아님
--   (과거 예보-실측 쌍의 검증은 G6 아카이브로 가능).

{{ config(materialized='table') }}

with frontier as (
    select max(bucket_at) as max_bucket_at
    from {{ ref('gold_transit_dong_15min') }}
),

areas as (
    select distinct area_cd, area_nm, admin_dong_code, gu_code
    from {{ source('seoul_citydata', 'gold_citydata_ppltn_forecast') }}
    where admin_dong_code is not null
),

-- G6 미래 행 = 날씨 예보(피벗·최신 발표 완료 형태).
future_weather as (
    select w.admin_dong_code, w.hour_at, w.temp_c, w.precip_prob, w.precip_type, w.is_precip
    from {{ ref('gold_transit_x_weather_dong_hourly') }} w
    cross join frontier f
    where w.hour_at > f.max_bucket_at
),

grain as (
    select
        a.area_cd,
        a.area_nm,
        a.admin_dong_code,
        a.gu_code,
        w.hour_at as target_hour_at,
        day_of_week(w.hour_at) as target_dow,
        hour(w.hour_at) as target_hh,
        day_of_week(w.hour_at) in (6, 7) as is_weekend,
        w.temp_c,
        w.precip_prob,
        w.precip_type,
        w.is_precip
    from areas a
    join future_weather w
        on a.admin_dong_code = w.admin_dong_code
)

select
    g.area_cd,
    g.area_nm,
    g.admin_dong_code,
    g.gu_code,
    g.target_hour_at,
    g.target_dow,
    g.is_weekend,
    -- 기대 인구(citydata 프로파일)
    f.expected_ppltn,
    f.peak_ppltn,
    f.ppltn_std,
    f.base_n as ppltn_base_n,
    -- 날씨 예보(그 시각 대상 최신 발표)
    g.temp_c,
    g.precip_prob,
    g.precip_type,
    g.is_precip as is_precip_expected,
    -- 평시 교통 기준선(G4 리듬 — 버스는 tier1)
    r.parking_occupancy_avg as rhythm_parking_occupancy,
    r.parking_base_n as rhythm_parking_base_n,
    r.bus_congestion_avg_t1 as rhythm_bus_congestion_t1,
    r.bus_base_n as rhythm_bus_base_n,
    -- 추천 플래그(v1 단순 규칙 — 헤더 주석)
    -- 리듬 조인 미스(신규 동·표본 부족)나 예보 결측이면 조건이 null 이 된다.
    -- 헤더가 약속한 '해석 가능한 불리언 3개' 계약을 지키려면 false 로 접어야 한다 —
    -- 안 그러면 `where not transit_recommended` 로 거르는 소비 측이 null 행을
    -- 조용히 잃는다(실측 8,160행 중 null 504행).
    coalesce(r.parking_occupancy_avg >= 0.8 and r.parking_base_n >= 4, false)
        as parking_busy_expected,
    coalesce(
        (r.parking_occupancy_avg >= 0.8 and r.parking_base_n >= 4)
        or g.is_precip,
        false
    ) as transit_recommended
from grain g
left join {{ source('seoul_citydata', 'gold_citydata_ppltn_forecast') }} f
    on f.area_cd = g.area_cd
   and f.is_weekend = g.is_weekend
   and f.hr = g.target_hh
left join {{ ref('gold_transit_dong_rhythm') }} r
    on r.admin_dong_code = g.admin_dong_code
   and r.dow = g.target_dow
   and r.hh = g.target_hh
