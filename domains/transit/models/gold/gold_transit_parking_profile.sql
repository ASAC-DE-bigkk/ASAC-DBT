-- gold_transit_parking_profile — 주차장별 요일×시간 점유 프로파일 (#288, G2 프로파일 축).
--
-- 한 행 = (parking_id, dow, hh)의 평시 점유. grain: (parking_id, dow, hh).
--   사용자 화면: "이 주차장은 평일 14시 만차 확률 85%, 20시 이후 여유".
--   gold_transit_parking_full_risk(스냅샷)가 '지금' 칸의 만차 확률을 여기서 조인한다.
--
-- ── 원천: 아카이브 전량 (#286 원칙 2) ───────────────────────────────────
--   gold_transit_parking_lot_15min 누적분 재집계. full_prob = 15분 버킷 중
--   occ_max >= 0.95(만차 터치) 비율 — 버킷 단위라 순간 만차도 잡힌다.
--   base_n(기여 버킷 수)으로 표본 신뢰도 노출(같은 칸 주 1회×4버킷 → 4주 ~16).
--
-- ── 재질(table) ────────────────────────────────────────────────────────
--   리듬(G4 #287)과 같은 이유로 전량 재계산 — 원천이 영구 아카이브라 단순·정확.

{{ config(materialized='table') }}

select
    parking_id,
    day_of_week(bucket_at) as dow,
    hour(bucket_at) as hh,
    count(*) as base_n,
    avg(occ_avg) as occ_avg,
    avg(case when occ_max >= 0.95 then 1.0 else 0.0 end) as full_prob
from {{ ref('gold_transit_parking_lot_15min') }}
where occ_avg is not null
group by parking_id, day_of_week(bucket_at), hour(bucket_at)
