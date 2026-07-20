-- dim_transit_bus_route_tier — 버스 노선의 수집 티어 분류 (#286, 수집 정책은 ASAC-DAG #440).
--
-- 한 행 = 최근 7일 내 관측된 버스 노선 1개. grain: bus_route_id.
--
-- ── 왜 관측 기반인가 ────────────────────────────────────────────────────
--   티어의 원천 정의(routeType: 3 간선·6 광역 = tier1)는 R2 reference
--   (reference/transit/bus_routes/latest.json)에만 있고 웨어하우스엔 적재되지 않는다.
--   여기서는 수집 결과의 관측 패턴으로 역산한다: tier1 은 매 30분(전 시간대) 수집,
--   tier2 는 BUS_TIER2_HOURS(기본 07·13·19시 KST) 정각 런에만 수집되므로,
--   최근 7일간 등장한 '시간대(hour) 종류 수'가 티어를 가른다.
--     tier2 정상 상한 = tier2 시각 수(기본 3, 런이 정각 전반부에만 돌아 spill 없음)
--     tier1 실측 ≈ 운행시간대 전부(~19종)
--   임계 12 인 이유: 티어링 배포 직후 과도기(2026-07-20 실측)엔 직전의 전 노선 간헐
--   수집(00시·09~12시 등)이 7일 윈도에 남아 tier2 노선도 시간대 5~6종 + tier2 시각
--   3종 ≈ 8~9종까지 도달한다 — 임계 8 이면 과도기 오분류. 12 는 그 위·tier1(~19종)
--   아래의 안전 마진(tier2 시각을 env 로 늘려도 여유). 한계: 운행시간이 짧은 심야
--   전용 노선(예: N버스, ~7시간대)은 tier1 이어도 2로 분류될 수 있음 — 시간대 비교
--   파생에서 빠질 뿐 전 티어 지표에는 포함되므로 안전한 방향의 오류다. reference 를
--   웨어하우스로 적재하는 정공법이 생기면 이 모델은 그 조인으로 대체 가능.
--
-- ── 소비 계약 ───────────────────────────────────────────────────────────
--   기반 아카이브 gold 가 빌드 시점에 조인해 tier 를 스탬프한다(#286 원칙 ①).
--   시간대 비교 지표(리듬·프로파일)는 tier=1 만 필터(원칙 ②). 최근 7일 무관측
--   노선은 이 dim 에 없음 → 조인 miss 는 tier null 로 남기고 tier1 집계에서 제외.
--
-- ── 매 빌드 전체 재계산(table) ──────────────────────────────────────────
--   분류 윈도가 '최근 7일' 슬라이딩이라 증분이 무의미. silver 7일치 스캔은 수십만 행
--   수준이라 매시 재계산 비용이 낮고, 수집 정책 변경(#440 env 조정)에 자동 추종한다.
--   기준 시각은 벽시계가 아니라 max(event_at) — 수집이 멈춰도 분류가 무너지지 않는다.

{{ config(materialized='table') }}

with recent as (
    select bus_route_id, event_at
    from {{ ref('silver_transit_bus_position') }}
    where event_at >= (
        select max(event_at) - interval '7' day
        from {{ ref('silver_transit_bus_position') }}
    )
)

select
    bus_route_id,
    count(distinct hour(event_at)) as obs_hour_kind_cnt,
    case when count(distinct hour(event_at)) >= 12 then 1 else 2 end as tier,
    count(*) as obs_cnt_7d,
    max(event_at) as last_event_at
from recent
group by bus_route_id
