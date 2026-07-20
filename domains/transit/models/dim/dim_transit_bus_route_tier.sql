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
--     tier1 = 수집 창의 매 시간 관측 → 창 크기와 같다(현행 19종: 00시 + 06~23시)
--     tier2 = BUS_TIER2_HOURS 시각에만 관측 → 2종(기본 09·19시)
--
--   임계 {{ var('transit_bus_tier1_min_hour_kinds') }} 의 근거: 수집 시간창(ASAC-DAG
--   #440 후속)이 24시간에서 19시간으로 줄면서 tier1 의 관측 시간대 종류도 19종으로
--   줄었다. 임계는 두 군집(19 vs 2) 사이에서 **낮은 쪽에 가깝게** 잡는다 —
--   높게 잡으면 수집 장애 한 번에 tier1 이 통째로 tier2 로 오분류되고, 그 기간의
--   bus_*_t1 집계는 원본이 주 단위로 삭제돼 소급 복구가 불가능하기 때문이다.
--   6 이면 하루치(19종 중 최소 6시간) 관측만 남아도 tier1 판정이 유지되고,
--   tier2(2종)와는 여전히 3배 차이라 오검출도 없다.
--   한계: 운행시간이 짧은 심야 전용 노선(N버스 등)은 tier1 이어도 2로 분류될 수 있다
--   — 시간대 비교 파생에서 빠질 뿐 전 티어 지표에는 포함되므로 안전한 방향의 오류다.
--   reference(routeType)를 웨어하우스로 적재하는 정공법이 생기면 이 모델은 그 조인으로
--   대체 가능하다(그때 이 휴리스틱은 검증용으로만 남긴다).
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
    case
        when count(distinct hour(event_at)) >= {{ var('transit_bus_tier1_min_hour_kinds') }}
        then 1 else 2
    end as tier,
    count(*) as obs_cnt_7d,
    max(event_at) as last_event_at
from recent
group by bus_route_id
