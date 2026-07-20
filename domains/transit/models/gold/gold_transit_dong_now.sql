-- gold_transit_dong_now — "지금 우리 동네 교통" 실시간 스코어카드 (#289, G1).
--
-- 한 행 = 행정동 1개의 최신 교통 상태. grain: admin_dong_code.
--   소스(버스·지하철·주차)별로 "최근 24시간 내 가장 최신 관측 버킷"의 지표 + 관측 시각을
--   나란히 놓고, 사용자 등급(혼잡 상/중/하, 주차 여유 %, 대기 분)으로 변환해 노출한다.
--
-- ── 소스별 독립 최신(3원 outer) ────────────────────────────────────────
--   한 동에서 주차는 5분 전, 버스는 40분 전(tier2 동은 수 시간 전)이 최신일 수 있다.
--   같은 버킷으로 묶으면 오래된 소스가 최신 버킷에서 null 이 되므로, 소스별로
--   "그 소스가 관측된 마지막 버킷"을 따로 뽑아 결합한다(아카이브 #67·#286 의 outer 관례).
--
-- ── freshness 표기(원칙 ③, #440) ───────────────────────────────────────
--   *_last_event_at(실제 관측 시각)이 곧 사용자 표기("N분 전 관측")의 근거다.
--   버스는 전 티어 사용 — tier2 만 다니는 동은 관측이 오래됐음을 숨기지 않고 보여준다.
--   여기서 벽시계와의 차이(경과분)를 계산하지 않는 이유: 이 테이블은 변환 주기마다
--   재생성되는 스냅샷이라, 경과 시간은 조회 시점 기준으로 소비 측이 계산해야 정확하다.
--
-- ── 등급 변환 ──────────────────────────────────────────────────────────
--   bus_congestion_grade: 원천 congestion 값역 3(여유)/4(보통)/5(혼잡) 평균 기준
--     <3.5 '여유', <4.5 '보통', 이상 '혼잡' (0='정보없음'은 아카이브에서 이미 제외).
--   parking_avail_pct: (1 - 점유율)×100 반올림.
--   subway_wait_min: 접근 중 열차 평균 잔여 도착초 → 분(1자리).
--
-- ── 재질(table) ────────────────────────────────────────────────────────
--   최신 스냅샷 파생이라 이력 없음 → 아카이브(gold_transit_dong_15min)에서 매 변환마다
--   전체 재생성(24h 윈도 스캔 ~4만 행, 저렴). full-refresh 가드 불필요(원본이 아카이브).
--   기준 시각은 벽시계가 아니라 아카이브 프런티어(max bucket_at) — 수집이 멈추면
--   '멈춘 시점의 최신'이 유지되고 last_event_at 표기가 정직하게 오래됨을 드러낸다.

{{ config(materialized='table') }}

with frontier as (
    select max(bucket_at) as max_bucket_at
    from {{ ref('gold_transit_dong_15min') }}
),

recent as (
    select g.*
    from {{ ref('gold_transit_dong_15min') }} g
    cross join frontier f
    where g.bucket_at >= f.max_bucket_at - interval '24' hour
),

bus_latest as (
    select
        admin_dong_code,
        max_by(bus_congestion_avg, bucket_at) as bus_congestion_avg,
        max_by(bus_full_ratio, bucket_at) as bus_full_ratio,
        max_by(bus_veh_cnt, bucket_at) as bus_veh_cnt,
        max(bus_last_event_at) as bus_last_event_at
    from recent
    where bus_obs_cnt > 0
    group by admin_dong_code
),

subway_latest as (
    select
        admin_dong_code,
        max_by(subway_wait_avg_s, bucket_at) as subway_wait_avg_s,
        max_by(subway_arrival_cnt, bucket_at) as subway_arrival_cnt,
        max(subway_last_event_at) as subway_last_event_at
    from recent
    where subway_arrival_cnt > 0
    group by admin_dong_code
),

parking_latest as (
    select
        admin_dong_code,
        max_by(parking_occupancy_avg, bucket_at) as parking_occupancy_avg,
        max_by(parking_lot_cnt, bucket_at) as parking_lot_cnt,
        max_by(parking_full_lot_cnt, bucket_at) as parking_full_lot_cnt,
        max(parking_last_event_at) as parking_last_event_at
    from recent
    where parking_lot_cnt > 0
    group by admin_dong_code
),

grain as (
    select admin_dong_code from bus_latest
    union
    select admin_dong_code from subway_latest
    union
    select admin_dong_code from parking_latest
)

select
    g.admin_dong_code,
    m.admin_dong,
    m.gu_code,
    m.gu,
    -- 버스(전 티어 — 커버리지 우선, 관측 시각 표기 필수)
    b.bus_congestion_avg,
    case
        when b.bus_congestion_avg is null then null
        when b.bus_congestion_avg < 3.5 then '여유'
        when b.bus_congestion_avg < 4.5 then '보통'
        else '혼잡'
    end as bus_congestion_grade,
    b.bus_full_ratio,
    b.bus_veh_cnt,
    b.bus_last_event_at,
    -- 지하철(실시간 6역 4개 동 한정 — 대부분 동에서 null 정상)
    round(s.subway_wait_avg_s / 60.0, 1) as subway_wait_min,
    s.subway_arrival_cnt,
    s.subway_last_event_at,
    -- 주차
    p.parking_occupancy_avg,
    round((1 - p.parking_occupancy_avg) * 100) as parking_avail_pct,
    p.parking_lot_cnt,
    p.parking_full_lot_cnt,
    p.parking_last_event_at
from grain g
left join bus_latest b on g.admin_dong_code = b.admin_dong_code
left join subway_latest s on g.admin_dong_code = s.admin_dong_code
left join parking_latest p on g.admin_dong_code = p.admin_dong_code
left join {{ ref('asac_axes', 'dim_admin_dong') }} m
    on g.admin_dong_code = m.admin_dong_code
