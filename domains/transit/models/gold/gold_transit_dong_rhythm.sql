-- gold_transit_dong_rhythm — 동별 요일×시간 교통 리듬 히트맵 (#287, G4).
--
-- 한 행 = (admin_dong_code, dow, hh)의 평시 프로파일. grain: (admin_dong_code, dow, hh).
--   dow = day_of_week(1=월 … 7=일, ISO), hh = 0~23 (모두 KST 벽시계 bucket_at 기준).
--   사용자 화면: "우리 동네는 금요일 18시가 일주일 중 최악" 히트맵. G1 '평시 대비'와
--   G10 예측 카드의 기준선(baseline)으로도 소비된다.
--
-- ── 원천: 아카이브 gold 전량 (#286 원칙 2) ──────────────────────────────
--   원본이 주 경계 삭제라 silver 로는 요일당 표본 최대 1개 — 반드시
--   gold_transit_dong_15min 누적분에서 파생한다. 아카이브가 쌓일수록 표본이 늘어
--   프로파일이 좋아진다(운영 초기 몇 주는 표본 부족 — base 컬럼으로 노출).
--
-- ── 버스 tier1 한정 (#440 원칙 ②) ───────────────────────────────────────
--   이 모델의 본질이 시간대 간 비교라 버스는 *_t1 만 소비한다. 전 티어를 섞으면
--   tier2 수집 시각(07·13·19시)에 표본 구성이 달라져 가짜 패턴이 생긴다.
--   집계는 관측수 가중(15분 버킷 단순 평균은 관측 적은 버킷 과대대표).
--
-- ── 표본 수 노출 ────────────────────────────────────────────────────────
--   *_base_n = 해당 (동,요일,시간) 칸에 기여한 15분 버킷 수(소스별). 같은 요일·시간이
--   주 1회 × 4버킷이므로 4주 누적 시 칸당 ~16. 소비 측이 임계(예: 8 미만 '표본 부족'
--   배지)를 정해 신뢰도를 판단한다 — 모델이 자의적으로 걸러내지 않는다.
--
-- ── 재질(table) ────────────────────────────────────────────────────────
--   아카이브 전량 재집계(현재 ~18만 행 → 동×요일×시간 ~7만 행)로 매 변환 재생성.
--   증분으로 만들면 요일 칸의 러닝 평균 갱신 로직이 필요해져 복잡도만 는다 —
--   원천(아카이브)이 영구 보존이므로 전량 재계산이 단순하고 정확하다.

{{ config(materialized='table') }}

with buckets as (
    select
        admin_dong_code,
        day_of_week(bucket_at) as dow,
        hour(bucket_at) as hh,
        bus_obs_cnt_t1,
        bus_congestion_avg_t1,
        bus_full_ratio_t1,
        subway_arrival_cnt,
        subway_wait_avg_s,
        parking_lot_cnt,
        parking_occupancy_avg,
        parking_full_lot_cnt
    from {{ ref('gold_transit_dong_15min') }}
)

select
    admin_dong_code,
    dow,
    hh,
    -- 버스(tier1 한정, 관측수 가중)
    count(case when bus_obs_cnt_t1 > 0 then 1 end) as bus_base_n,
    sum(bus_obs_cnt_t1) as bus_obs_sum_t1,
    case when sum(case when bus_congestion_avg_t1 is not null then bus_obs_cnt_t1 end) > 0
         then sum(bus_congestion_avg_t1 * bus_obs_cnt_t1)
              / sum(case when bus_congestion_avg_t1 is not null then bus_obs_cnt_t1 end)
    end as bus_congestion_avg_t1,
    case when sum(case when bus_full_ratio_t1 is not null then bus_obs_cnt_t1 end) > 0
         then sum(bus_full_ratio_t1 * bus_obs_cnt_t1)
              / sum(case when bus_full_ratio_t1 is not null then bus_obs_cnt_t1 end)
    end as bus_full_ratio_t1,
    -- 지하철
    count(case when subway_arrival_cnt > 0 then 1 end) as subway_base_n,
    avg(subway_wait_avg_s) as subway_wait_avg_s,
    -- 주차
    count(case when parking_lot_cnt > 0 then 1 end) as parking_base_n,
    avg(parking_occupancy_avg) as parking_occupancy_avg,
    avg(cast(parking_full_lot_cnt as double)) as parking_full_lot_avg
from buckets
group by admin_dong_code, dow, hh
