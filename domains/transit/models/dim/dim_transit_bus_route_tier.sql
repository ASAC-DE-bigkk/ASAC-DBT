-- dim_transit_bus_route_tier — 버스 노선의 수집 티어 (#315, 원천은 ASAC-DAG #440·#471).
--
-- 한 행 = 버스 노선 1개. grain: bus_route_id. tier: 1=간선·광역(dense 수집), 2=그 외.
--
-- ── tier 는 routeType 원천 (#471) ───────────────────────────────────────
--   tier 는 bronze_bus_route_master 가 이미 담고 있다 — DAG 이 수집 정책
--   (config.BUS_TIER1_TYPES: routeType 3 간선·6 광역)으로 계산해 넣는다. 여기서는
--   그 값을 그대로 노출한다. tier 정의의 단일 출처가 collector 정책이므로 dbt 에서
--   재계산하지 않는다(값 복제 시 두 곳이 어긋날 위험).
--
--   이전(#286)에는 tier 를 '수집 런 시각'으로 역산했다 — tier2 는 정시 런에만 실리니
--   dense 런 등장 여부로 tier1 을 판정. 그 방식은 dense 창에 운행하지 않은 tier1 을
--   tier2 로 놓쳤다(2026-07-21 실측: 관측 140 vs 원천 165, 갭 25 = 미운행 tier1).
--   원천 조인으로 그 갭이 사라지고, 운행 여부·관측 커버리지와 무관하게 정확해진다.
--
-- ── 관측 tier 는 검증용으로 병기 ────────────────────────────────────────
--   observed_tier 는 옛 역산 로직(아카이브 개시일 이후 dense 런 등장)을 그대로 남긴
--   것이다. 분류에는 쓰지 않고, tier_mismatch 로 원천과 어긋나는 노선을 드러낸다:
--     - 정상 불일치: 원천 tier1 인데 아직 dense 창에 안 잡힘(observed 2) → 곧 해소
--     - 이상 신호: 원천 tier2 인데 dense 런에 반복 등장(observed 1) → 수집 정책과
--       reference 불일치(BUS_TIER1_TYPES 변경 미반영 등) 의심
--   즉 원천을 신뢰하되 수집 실측으로 원천을 감시하는 안전망이다.
--
-- ── 매 빌드 전체 재계산(table) ──────────────────────────────────────────
--   마스터가 주간 전체 교체라 dim 도 그 스냅샷을 그대로 물화한다. 관측 병기 때문에
--   silver 를 개시일 이후로 스캔하나, 집계 후 grain 이 노선 단위라 가볍다.

{{ config(materialized='table') }}

-- 마스터는 load_date 단위 멱등 적재(#471) — 최신 스냅샷만 취한다. 이번 주 적재가
-- 실패해 비어도 max(load_date)는 마지막 성공분을 가리켜 tier 가 유지된다.
with latest_load as (
    select max(load_date) as load_date
    from {{ source('transit_bronze', 'bus_route_master') }}
),

source_tier as (
    select
        m.bus_route_id,
        m.bus_route_nm,
        m.route_type,
        m.tier,
        m.load_date,
        m.collected_at
    from {{ source('transit_bronze', 'bus_route_master') }} m
    join latest_load l on m.load_date = l.load_date
),

-- 검증용: 개시일 이후 '정시(:00)가 아닌 스케줄 런'에 등장 = dense 수집 관측 = tier1 신호.
observed as (
    select
        bus_route_id,
        count(case
            when dag_run_id like 'scheduled\_\_%' escape '\'
             and regexp_extract(dag_run_id, 'T\d{2}:(\d{2}):', 1) <> '00'
            then 1
        end) as dense_run_obs_cnt,
        max(event_at) as last_event_at
    from {{ ref('silver_transit_bus_position') }}
    where event_at >= timestamp '{{ var("transit_archive_start_at") }}'
    group by bus_route_id
)

select
    s.bus_route_id,
    s.bus_route_nm,
    s.route_type,
    s.tier,
    -- 검증 컬럼(분류 미사용)
    case when o.dense_run_obs_cnt > 0 then 1 else 2 end as observed_tier,
    o.dense_run_obs_cnt,
    (o.dense_run_obs_cnt > 0 and s.tier <> 1) as tier_mismatch,
    o.last_event_at,
    s.load_date,
    s.collected_at
from source_tier s
left join observed o on s.bus_route_id = o.bus_route_id
