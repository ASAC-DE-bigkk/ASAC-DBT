-- gold_transit_bus_route_comfort — 노선×구간별 "몇 시에 타면 앉아 가나" (#288, G3).
--
-- 한 행 = (bus_route_id, sect_ord, dow, hh)의 평시 쾌적도. grain: (bus_route_id,
--   sect_ord, dow, hh). 사용자 화면: "272번 성수→건대 구간, 8시대 혼잡 4.2/5".
--
-- ── tier1 한정 (#440 원칙 ②) ────────────────────────────────────────────
--   시간대 비교 모델이므로 tier=1(간선·광역, 전 시간대 30분 수집)만 집계한다.
--   tier2 는 하루 3회 관측이라 시간대 프로파일 자체가 성립하지 않는다(이슈 #288).
--   tier 미상(null — dim 미등재)은 보수적으로 제외.
--
-- ── 원천: 아카이브 전량 (#286 원칙 2) ───────────────────────────────────
--   gold_transit_route_section_30min 누적분 재집계, 관측수 가중. base_n(기여 30분
--   버킷 수)으로 표본 신뢰도 노출 — 같은 칸 주 1회×2버킷 → 4주 ~8.
--
-- ── 재질(table) ────────────────────────────────────────────────────────
--   리듬(G4)·주차 프로파일과 같은 전량 재계산 관례.

{{ config(materialized='table') }}

select
    bus_route_id,
    sect_ord,
    day_of_week(bucket_at) as dow,
    hour(bucket_at) as hh,
    count(*) as base_n,
    sum(obs_cnt) as obs_sum,
    case when sum(case when congestion_avg is not null then obs_cnt end) > 0
         then sum(congestion_avg * obs_cnt)
              / sum(case when congestion_avg is not null then obs_cnt end)
    end as congestion_avg,
    case when sum(case when full_ratio is not null then obs_cnt end) > 0
         then sum(full_ratio * obs_cnt)
              / sum(case when full_ratio is not null then obs_cnt end)
    end as full_ratio,
    case when sum(case when stop_ratio is not null then obs_cnt end) > 0
         then sum(stop_ratio * obs_cnt)
              / sum(case when stop_ratio is not null then obs_cnt end)
    end as stop_ratio
from {{ ref('gold_transit_route_section_30min') }}
where tier = 1
group by bus_route_id, sect_ord, day_of_week(bucket_at), hour(bucket_at)
