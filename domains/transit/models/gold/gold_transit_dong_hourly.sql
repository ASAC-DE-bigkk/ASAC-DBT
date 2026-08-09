-- gold_transit_dong_hourly — 동×시간대 교통 상태판 (#67).
--
-- 한 행 = (admin_dong_code, hour_at) 한 조합의 버스·지하철·주차 지표 나란히.
--   grain: (admin_dong_code, hour_at). hour_at = date_trunc('hour', event_at) — silver 의
--   event_at 은 KST 벽시계(tz 없는 timestamp)이므로 시간 절삭도 KST 벽시계 유지('_at' 계약 부합).
--
-- ── 소스 결합(3원 outer) ────────────────────────────────────────────────
--   버스·지하철·주차는 (동, 시간) 조합이 서로 다르다(버스=간선 5노선 94개 동, 지하철=역 3곳
--   4개 동뿐, 주차=123개소 62개 동). 한 소스만 있는 조합도 행을 만들어야 하므로 full outer 결합이
--   필요. 여기서는 세 집계의 (동,시간) 키를 union(중복 제거)해 키 집합을 만들고 각 집계를 left join
--   한다 — 3-way full outer join 과 동치이며 조인 술어 중복(coalesce 키)이 없어 더 단순하다.
--   지하철은 4개 동에만 존재해 대부분의 (동,시간) 행에서 subway_* 가 null — 정상(커버리지 한계).
--
-- ── admin_dong_code null 제외 ───────────────────────────────────────────
--   공간축 미부착(admin_dong_code null) 행은 동 그레인을 만들 수 없어 각 소스에서 제외한다.
--   실측(dev, 2026-06-30~07-07): 버스 0/36037, 지하철 0/7668, 주차 1460/39785(≈3.7%) 제외.
--   주차만 좌표 결손 lot 이 있어 제외분 발생, 버스·지하철은 전건 부착.
--
-- ── 시간 신선도 ─────────────────────────────────────────────────────────
--   silver 3종은 이미 #66 게이트(event_at <= utc_to_kst(ingested_at)+스큐)로 미래 event_at 이
--   정화돼 있다. 따라서 gold 에서 추가 시간 필터는 불필요 — 정화된 silver 만 소비한다.
--
-- ── 증분(incremental merge) ─────────────────────────────────────────────
--   unique_key=(admin_dong_code, hour_at). lookback 은 silver 관례(-2h)보다 넉넉한 -3h.
--   근거: gold 는 시간 버킷 단위 재집계라, 한 hour_at 버킷은 그 시각의 silver 행이 늦게 도착하면
--   전체를 다시 집계해야 한다. 임계를 시간 경계(date_trunc)에 맞춰 max(hour_at)-3h 로 잡으면
--   event_at >= hour_at 성질상 최근 3개 완성 시간 버킷(+진행 중 시간)이 항상 완전한 silver 로
--   재계산된다(부분 집계 방지). silver 자체의 -2h lookback + 시간 경계 여유 1h 를 합쳐 -3h.
--   merge 는 재집계된 버킷만 갱신, 그 이전 버킷은 안정적이라 건드리지 않는다.

-- sorted_by(#482): 근거는 silver_transit_subway_arrival 동일 주석 참조.
-- (day 파티셔닝은 d9f38a7 당시 데이터 보유 중이라 제외됐던 테이블 — 여기서도 안 건드림.)
{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['admin_dong_code', 'hour_at'],
    properties={'sorted_by': "ARRAY['hour_at']"},
) }}

-- 증분 하한(시간 경계): max(hour_at) - 3h. 최초 빌드는 전건.
-- 각 소스 CTE 의 `where admin_dong_code is not null` 뒤에 붙으므로 `and` 로 이어붙인다.
{%- set incr_filter %}
{% if is_incremental() %}
and event_at >= (
    select coalesce(max(hour_at), timestamp '1970-01-01') - interval '3' hour
    from {{ this }}
)
{% endif %}
{%- endset %}

with bus_src as (
    select admin_dong_code, event_at, veh_id, congestion, is_full, stop_flag
    from {{ ref('silver_transit_bus_position') }}
    where admin_dong_code is not null
      {{ incr_filter }}
),

bus_agg as (
    select
        admin_dong_code,
        date_trunc('hour', event_at) as hour_at,
        count(*) as bus_obs_cnt,
        count(distinct veh_id) as bus_veh_cnt,
        -- congestion=0 은 '정보없음'이라 평균에서 제외(실측 값역 0/3/4/5, 0 이 625/36037건).
        {{ transit_bus_congestion_avg() }} as bus_congestion_avg,
        avg(cast(is_full as double)) as bus_full_ratio,
        avg(cast(stop_flag as double)) as bus_stop_ratio
    from bus_src
    group by admin_dong_code, date_trunc('hour', event_at)
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
        date_trunc('hour', event_at) as hour_at,
        count(*) as subway_arrival_cnt,
        -- barvl_dt_sec(도착예정 초). 0 = 이미 도착/진입한 열차(대기 아님)라 '대기시간 평균'에서 제외한다
        --   (실측 3409/7668 ≈ 44% 가 0 — 포함하면 평균이 절반 이하로 왜곡). 이 지표는 '접근 중 열차의
        --   평균 잔여 도착시간(초)'을 뜻한다. null 은 avg 가 자동 무시.
        avg(case when barvl_dt_sec > 0 then cast(barvl_dt_sec as double) end) as subway_wait_avg_s,
        sum(is_last_train) as subway_last_train_cnt
    from subway_src
    group by admin_dong_code, date_trunc('hour', event_at)
),

parking_src as (
    select
        admin_dong_code,
        event_at,
        parking_id,
        -- 점유율은 현재대수/총면수. 둘 다 유효 & 총면수>0 인 관측만(그 외 null → 평균 무시).
        -- (과거 소수문자열 캐스트 결손으로 전건 null 이던 시기가 있었음 — #72 매크로
        --  transit_int_from_numeric_str 로 해소, 2026-07-20 실측 전건 non-null 확인 #286.)
        {{ transit_parking_occ_ratio() }} as occ_ratio
    from {{ ref('silver_transit_parking') }}
    where admin_dong_code is not null
      {{ incr_filter }}
),

-- 개소(lot) 단위로 먼저 접어 시간 내 대표값을 뽑는다: 평균 점유율 + 최대 점유율(만차 판정용).
parking_lot as (
    select
        admin_dong_code,
        date_trunc('hour', event_at) as hour_at,
        parking_id,
        avg(occ_ratio) as lot_occ_mean,
        max(occ_ratio) as lot_occ_max
    from parking_src
    group by admin_dong_code, date_trunc('hour', event_at), parking_id
),

parking_agg as (
    select
        admin_dong_code,
        hour_at,
        -- 관측 개소 수(동×시간에 등장한 distinct lot). lot 그레인이라 count(*) = distinct 개소.
        count(*) as parking_lot_cnt,
        -- 동×시간 평균 점유율 = 개소별 평균 점유율의 평균(개소 동등가중). 관측 잦은 lot 이 과대대표
        --   되지 않게 lot 단위로 먼저 접은 뒤 평균.
        avg(lot_occ_mean) as parking_occupancy_avg,
        -- 만차 개소 수 = 시간 내 최대 점유율 >= 0.95 인 개소 수.
        sum(case when lot_occ_max >= 0.95 then 1 else 0 end) as parking_full_lot_cnt
    from parking_lot
    group by admin_dong_code, hour_at
),

-- 3원 outer 결합용 키 집합(중복 제거 union).
grain as (
    select admin_dong_code, hour_at from bus_agg
    union
    select admin_dong_code, hour_at from subway_agg
    union
    select admin_dong_code, hour_at from parking_agg
)

select
    g.admin_dong_code,
    g.hour_at,
    -- 버스
    b.bus_obs_cnt,
    b.bus_veh_cnt,
    b.bus_congestion_avg,
    b.bus_full_ratio,
    b.bus_stop_ratio,
    -- 지하철
    s.subway_arrival_cnt,
    s.subway_wait_avg_s,
    s.subway_last_train_cnt,
    -- 주차
    p.parking_lot_cnt,
    p.parking_occupancy_avg,
    p.parking_full_lot_cnt
from grain g
left join bus_agg b
    on g.admin_dong_code = b.admin_dong_code and g.hour_at = b.hour_at
left join subway_agg s
    on g.admin_dong_code = s.admin_dong_code and g.hour_at = s.hour_at
left join parking_agg p
    on g.admin_dong_code = p.admin_dong_code and g.hour_at = p.hour_at
