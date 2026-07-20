-- gold_transit_parking_full_risk — 주차장별 "지금 가면 자리 있나 + 만차 임박" (#288, G2).
--
-- 한 행 = 주차장 1개소의 현재 스냅샷. grain: parking_id.
--   사용자 화면: "현재 88%, 채워지는 속도로 30분 내 만차 예상 — 이 시간대 만차 확률 85%".
--
-- ── 변화율(5분 관측 덕에 가능한 지표, #440 이전 20분 주기에선 불가) ──────
--   최근 1시간의 **연속** 버킷(lot 자신의 last_bucket_at -45분 이내 = 15분 버킷 4개)
--   occ_last 시계열에서 선형 추세를 잡는다. '관측된 최근 4건'으로 잡으면 결측이 있는
--   lot 은 그 4건이 수 시간에 걸쳐 기울기가 희석되는데도 가드를 통과해버린다:
--   rate/min = (최신 occ_last - 최초 occ_last) / 경과분. 양(+)이면 채워지는 중.
--   minutes_to_full = (0.95 - 현재 점유율) / rate (rate>0 일 때만, 0.95=만차 판정선
--   — 아카이브·프로파일과 동일 임계). 4버킷 미만 관측이면 rate null(신규·결측 lot).
--
-- ── '이 시간대' 만차 확률 ───────────────────────────────────────────────
--   gold_transit_parking_profile 을 스냅샷 시각(프런티어 버킷)의 (dow, hh) 칸으로 조인.
--   profile_base_n 을 함께 노출 — 표본 얇은 칸(운영 초기)은 소비 측이 배지 처리.
--
-- ── 재질(table)·기준 시각 ───────────────────────────────────────────────
--   dong_now(G1)와 동일: 매 변환 재생성 스냅샷, 기준은 벽시계가 아니라 아카이브
--   프런티어(수집이 멈추면 last_event_at 이 정직하게 오래됨을 드러낸다).
--   경과분 계산은 조회 시점 기준으로 소비 측 몫.

{{ config(materialized='table') }}

with frontier as (
    select max(bucket_at) as max_bucket_at
    from {{ ref('gold_transit_parking_lot_15min') }}
),

-- 최근 24h 관측 버킷(occ 유효분만).
recent as (
    select p.*
    from {{ ref('gold_transit_parking_lot_15min') }} p
    cross join frontier f
    where p.bucket_at >= f.max_bucket_at - interval '24' hour
      and p.occ_last is not null
),

-- lot 별 최신 상태.
latest as (
    select
        parking_id,
        max_by(admin_dong_code, bucket_at) as admin_dong_code,
        max_by(gu_code, bucket_at) as gu_code,
        max_by(occ_last, bucket_at) as occ_now,
        max_by(capacity_last, bucket_at) as capacity_now,
        max_by(bucket_at, bucket_at) as last_bucket_at,
        max(last_event_at) as last_event_at
    from recent
    group by parking_id
),

-- lot 별 변화율: 자신의 최신 버킷에서 45분 이내(연속일 때만 4개가 찬다)의 처음↔끝 차이.
rate_window as (
    select r.parking_id, r.bucket_at, r.occ_last
    from recent r
    join latest l on r.parking_id = l.parking_id
    where r.bucket_at >= l.last_bucket_at - interval '45' minute
),

rate as (
    select
        parking_id,
        count(*) as rate_base_n,
        case when count(*) >= 4
              and date_diff('minute', min_by(bucket_at, bucket_at), max_by(bucket_at, bucket_at)) > 0
             then (max_by(occ_last, bucket_at) - min_by(occ_last, bucket_at))
                  / cast(date_diff('minute', min_by(bucket_at, bucket_at), max_by(bucket_at, bucket_at)) as double)
        end as occ_rate_per_min
    from rate_window
    group by parking_id
)

select
    l.parking_id,
    d.parking_name,
    l.admin_dong_code,
    l.gu_code,
    d.latitude,
    d.longitude,
    l.occ_now,
    round((1 - l.occ_now) * 100) as avail_pct,
    l.capacity_now,
    -- 잔여 대수 추정(총면수 × 여유율).
    round(l.capacity_now * (1 - l.occ_now)) as avail_lot_est,
    r.occ_rate_per_min,
    r.rate_base_n,
    -- 만차(0.95)까지 예상 분 — 채워지는 중(rate>0)일 때만. 이미 만차면 0.
    case
        when l.occ_now >= 0.95 then 0
        when r.occ_rate_per_min > 0
        then round((0.95 - l.occ_now) / r.occ_rate_per_min)
    end as minutes_to_full_est,
    -- '이 시간대' 평시 만차 확률(프로파일 조인, 프런티어 시각 칸).
    pf.full_prob as full_prob_now_slot,
    pf.base_n as profile_base_n,
    l.last_bucket_at,
    l.last_event_at
from latest l
left join rate r on l.parking_id = r.parking_id
-- 프로파일은 **그 lot 자신의 최신 관측 시각** 칸으로 조인한다. 전역 프런티어로 조인하면
-- 피드가 끊긴 lot 이 '09시 점유율 + 20시 만차확률' 처럼 서로 다른 시각의 값을 한 행에
-- 담아, 소비 측이 last_bucket_at 을 직접 대조하지 않는 한 앞뒤가 안 맞는 카드가 된다.
left join {{ ref('gold_transit_parking_profile') }} pf
    on l.parking_id = pf.parking_id
   and pf.dow = day_of_week(l.last_bucket_at)
   and pf.hh = hour(l.last_bucket_at)
left join {{ ref('dim_transit_parking') }} d
    on l.parking_id = d.parking_id
