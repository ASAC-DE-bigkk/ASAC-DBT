-- gold_transit_dong_15min — 동×15분 교통 상태 기반 아카이브 (#286).
--
-- 한 행 = (admin_dong_code, bucket_at) 한 조합의 버스·지하철·주차 지표 나란히.
--   grain: (admin_dong_code, bucket_at). bucket_at = 15분 버킷(KST 벽시계,
--   transit_time_bucket — '_at' 계약 부합). gold_transit_dong_hourly(#67)의 15분판이며,
--   구조(3원 outer 결합·null 동 제외·정화 silver 소비)는 hourly 와 동일 — 차이만 주석한다.
--
-- ── 왜 15분 grain 인가 (#286) ───────────────────────────────────────────
--   원본(R2 raw·bronze)은 주 경계(월~일 KST) 삭제(ASAC-DAG #369)라 이 테이블이
--   사실상의 영구 아카이브다. 지하철 3분·주차 5분 수집이라 15분 버킷당 지하철 ~5회,
--   주차 ~3회 관측이 담긴다. 버스는 티어링(#440) 후 30분 주기라 15분 버킷의 절반이
--   빈 것이 정상 — 버스 축 아카이브는 gold_transit_route_section_30min 이 담당하고,
--   여기의 버스 컬럼은 동 단위 상태판(G1)·리듬(G4) 용도다.
--
-- ── 버스 티어 분리(원칙 ①·②, #440) ─────────────────────────────────────
--   bus_* 는 전 티어 집계(현재 상태·커버리지 용도 — 420개 동), bus_*_t1 은
--   dim_transit_bus_route_tier 조인으로 tier1(간선·광역, 전 시간대 30분 수집)만 집계.
--   tier2 는 07·13·19시에만 관측돼 시간대 비교 시 표본 구성이 달라지므로, 시간대끼리
--   비교하는 파생(리듬 G4·프로파일·예측 G10)은 반드시 *_t1 만 소비한다.
--   dim 미등재 노선(최근 7일 무관측)은 tier null → 전 티어 집계에만 포함.
--
-- ── 소스별 최신 관측 시각(원칙 ③) ──────────────────────────────────────
--   *_last_event_at 은 버킷 내 소스별 max(event_at). 사용자향 '지금' 카드(G1)가
--   "N분 전 관측"을 정직하게 표기하는 근거 — 특히 버스 tier2 동은 수 시간 전일 수 있다.
--
-- ── 증분(incremental merge) + full-refresh 가드 ─────────────────────────
--   unique_key=(admin_dong_code, bucket_at), 임계 max(bucket_at)-3h (hourly #67 과
--   같은 근거: silver -2h lookback + 버킷 경계 여유 → 최근 완성 버킷들이 항상 완전한
--   silver 로 재집계). full_refresh=false 고정 — 원본이 주 단위로 사라지므로 재빌드는
--   지난주 이전 아카이브의 영구 소실이다. 스키마 변경 등으로 정말 재생성해야 하면
--   기존 테이블 백업(CTAS) 후 수동으로 진행할 것.

-- ── Iceberg 일 파티셔닝 ────────────────────────────────────────────────
--   MERGE 가 대상 전체 데이터파일을 훑지 않고 최근 파티션만 건드리게 하고, 하위
--   소비(24h 창·프런티어 산출·시간 롤업)의 시간 술어가 프루닝된다. 테이블이 비어
--   있는 지금 넣지 않으면 full_refresh=false 라 나중엔 CTAS 백업→재적재 수동
--   절차를 거쳐야 바꿀 수 있다.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['admin_dong_code', 'bucket_at'],
    full_refresh=false,
    properties={'partitioning': "ARRAY['day(bucket_at)']"},
) }}

{%- set incr_filter %}
-- 아카이브 개시일 하한(var transit_archive_start_at) — 정책 전환 전의 오염 구간
-- (silver grain 중복·무의미한 tier 스탬프)이 영구 아카이브로 유입되는 것을 막는다.
and event_at >= timestamp '{{ var("transit_archive_start_at") }}'
{% if is_incremental() %}
and event_at >= (
    select coalesce(max(bucket_at), timestamp '1970-01-01') - interval '3' hour
    from {{ this }}
)
{% endif %}
{%- endset %}

with bus_src as (
    select
        b.admin_dong_code,
        b.event_at,
        b.veh_id,
        b.congestion,
        b.is_full,
        b.stop_flag,
        t.tier
    from {{ ref('silver_transit_bus_position') }} b
    left join {{ ref('dim_transit_bus_route_tier') }} t
        on b.bus_route_id = t.bus_route_id
    -- event_at 은 조인 양측에서 b 에만 존재해 비한정 참조 모호성 없음(dim 은 last_event_at).
    where b.admin_dong_code is not null
      {{ incr_filter }}
),

bus_agg as (
    select
        admin_dong_code,
        {{ transit_time_bucket('event_at', 15) }} as bucket_at,
        -- 전 티어(현재 상태·커버리지 용도).
        count(*) as bus_obs_cnt,
        count(distinct veh_id) as bus_veh_cnt,
        -- congestion=0 은 '정보없음'이라 평균 제외(hourly #67 과 동일).
        avg(case when congestion is not null and congestion <> 0 then cast(congestion as double) end) as bus_congestion_avg,
        avg(cast(is_full as double)) as bus_full_ratio,
        avg(cast(stop_flag as double)) as bus_stop_ratio,
        -- tier1 한정(시간대 비교 파생 전용).
        count(case when tier = 1 then 1 end) as bus_obs_cnt_t1,
        count(distinct case when tier = 1 then veh_id end) as bus_veh_cnt_t1,
        avg(case when tier = 1 and congestion is not null and congestion <> 0 then cast(congestion as double) end) as bus_congestion_avg_t1,
        avg(case when tier = 1 then cast(is_full as double) end) as bus_full_ratio_t1,
        avg(case when tier = 1 then cast(stop_flag as double) end) as bus_stop_ratio_t1,
        max(event_at) as bus_last_event_at
    from bus_src
    group by admin_dong_code, {{ transit_time_bucket('event_at', 15) }}
),

subway_src as (
    select admin_dong_code, event_at, barvl_dt_sec, is_last_train
    from {{ ref('silver_transit_subway_arrival') }}
    where admin_dong_code is not null
      {{ incr_filter }}
),

subway_agg as (
    select
        admin_dong_code,
        {{ transit_time_bucket('event_at', 15) }} as bucket_at,
        count(*) as subway_arrival_cnt,
        -- barvl_dt_sec=0(도착/진입) 제외 — '접근 중 열차 평균 잔여 도착초'(hourly #67 과 동일).
        avg(case when barvl_dt_sec > 0 then cast(barvl_dt_sec as double) end) as subway_wait_avg_s,
        sum(is_last_train) as subway_last_train_cnt,
        max(event_at) as subway_last_event_at
    from subway_src
    group by admin_dong_code, {{ transit_time_bucket('event_at', 15) }}
),

parking_src as (
    select
        admin_dong_code,
        event_at,
        parking_id,
        -- 점유율 = 현재대수/총면수(둘 다 유효 & 총면수>0 만, 그 외 null → 평균 무시).
        case
            when now_prk_vhcl_cnt is not null
             and total_capacity is not null
             and total_capacity > 0
            then cast(now_prk_vhcl_cnt as double) / total_capacity
        end as occ_ratio
    from {{ ref('silver_transit_parking') }}
    where admin_dong_code is not null
      {{ incr_filter }}
),

-- 개소 단위로 먼저 접어 관측 잦은 lot 과대대표 방지(hourly #67 과 동일한 동등가중).
parking_lot as (
    select
        admin_dong_code,
        {{ transit_time_bucket('event_at', 15) }} as bucket_at,
        parking_id,
        avg(occ_ratio) as lot_occ_mean,
        max(occ_ratio) as lot_occ_max,
        max(event_at) as lot_last_event_at
    from parking_src
    group by admin_dong_code, {{ transit_time_bucket('event_at', 15) }}, parking_id
),

parking_agg as (
    select
        admin_dong_code,
        bucket_at,
        count(*) as parking_lot_cnt,
        avg(lot_occ_mean) as parking_occupancy_avg,
        sum(case when lot_occ_max >= 0.95 then 1 else 0 end) as parking_full_lot_cnt,
        max(lot_last_event_at) as parking_last_event_at
    from parking_lot
    group by admin_dong_code, bucket_at
),

-- 3원 outer 결합용 키 집합(중복 제거 union, hourly #67 과 동일).
grain as (
    select admin_dong_code, bucket_at from bus_agg
    union
    select admin_dong_code, bucket_at from subway_agg
    union
    select admin_dong_code, bucket_at from parking_agg
)

select
    g.admin_dong_code,
    g.bucket_at,
    -- 버스(전 티어)
    b.bus_obs_cnt,
    b.bus_veh_cnt,
    b.bus_congestion_avg,
    b.bus_full_ratio,
    b.bus_stop_ratio,
    -- 버스(tier1 한정 — 시간대 비교 파생 전용)
    b.bus_obs_cnt_t1,
    b.bus_veh_cnt_t1,
    b.bus_congestion_avg_t1,
    b.bus_full_ratio_t1,
    b.bus_stop_ratio_t1,
    b.bus_last_event_at,
    -- 지하철
    s.subway_arrival_cnt,
    s.subway_wait_avg_s,
    s.subway_last_train_cnt,
    s.subway_last_event_at,
    -- 주차
    p.parking_lot_cnt,
    p.parking_occupancy_avg,
    p.parking_full_lot_cnt,
    p.parking_last_event_at
from grain g
left join bus_agg b
    on g.admin_dong_code = b.admin_dong_code and g.bucket_at = b.bucket_at
left join subway_agg s
    on g.admin_dong_code = s.admin_dong_code and g.bucket_at = s.bucket_at
left join parking_agg p
    on g.admin_dong_code = p.admin_dong_code and g.bucket_at = p.bucket_at
