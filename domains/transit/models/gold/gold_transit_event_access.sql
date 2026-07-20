-- gold_transit_event_access — 행사장 가는 길 안내판 (#290, G7, × culture).
--
-- 한 행 = 진행·예정 행사 1건의 대중교통·주차 접근성. grain: event_ref.
--   사용자 화면: "이 공연장: 7호선 어린이대공원역 도보 5분, 공연시간대 인근 주차
--   만차 확률 90% → 대중교통 권장".
--
-- ── 대상 행사 ──────────────────────────────────────────────────────────
--   culture.gold_culture_event_schedule 중 좌표 보유 & 종료 전(event_end_date >=
--   current_date). 실측 ~950건 — 역 784·주차 850 과의 cross 거리 계산이 저렴하다.
--
-- ── 접근성(전 지역 즉시 제공) ───────────────────────────────────────────
--   최근접 지하철역·주차장은 dim(마스터, 전 노선 700+역) 기반 great_circle_distance —
--   실시간 커버리지(6역·주차 109개소)와 무관하게 전 행사에 제공된다(#290 계획대로
--   접근성 먼저). 도보 환산은 소비 측 몫(80m/분 관례).
--
-- ── 행사 시간대 주차 프로파일 ───────────────────────────────────────────
--   최근접 주차장의 gold_transit_parking_profile(#288)을 행사 시각 칸으로 조인.
--   evt_hh = hour(event_at), 시각 미상(다수)은 19시 근사(공연·행사 대표 시간대 —
--   가정임을 컬럼명·주석에 명시). 요일 축은 행사가 기간형(start~end)이라 특정할 수
--   없어 전 요일 평균 — "그 시간대 대략의 만차 경향"으로 읽어야 한다.
--   프로파일 미존재(실시간 미제공 lot)면 null = "정보 없음".
--
-- ── 재질(table) ────────────────────────────────────────────────────────
--   행사 집합이 날마다 바뀌는 스냅샷 파생 — 매 변환 전체 재생성. 아카이브 아님.

{{ config(materialized='table') }}

with events as (
    select
        event_ref,
        event_type,
        title,
        venue_name,
        event_start_date,
        event_end_date,
        event_at,
        -- 시각 미상 행사가 다수라 19시(공연·행사 대표 시간대)로 근사한다.
        -- 근사 여부를 플래그로 남기지 않으면 진짜 19시 행사와 구분할 수 없어,
        -- 소비 측이 '만차 확률 90%'를 걸러내거나 배지를 달 방법이 없다.
        coalesce(hour(event_at), 19) as evt_hh,
        event_at is null as is_evt_hh_imputed,
        admin_dong_code,
        gu,
        latitude,
        longitude
    from {{ source('culture', 'gold_culture_event_schedule') }}
    where latitude is not null
      and longitude is not null
      -- event_end_date 는 KST 달력 날짜인데 current_date 는 세션 타임존(UTC) 기준이라,
      -- UTC 세션에서 KST 00~09시에 빌드하면 어제 끝난 행사가 최대 9시간 더 노출된다.
      and event_end_date >= cast(at_timezone(current_timestamp, 'Asia/Seoul') as date)
),

stations as (
    select station_id, station_name, route, latitude, longitude
    from {{ ref('dim_transit_station') }}
    where latitude is not null and longitude is not null
),

parkings as (
    -- 좌표 0.0(미상) lot 다수(dim 주석) — 서울 위경도 범위로 유효 좌표만.
    select parking_id, parking_name, latitude, longitude
    from {{ ref('dim_transit_parking') }}
    where latitude between 37.0 and 38.0
      and longitude between 126.0 and 128.0
),

station_dist as (
    select
        e.event_ref,
        s.station_name,
        s.route,
        great_circle_distance(e.latitude, e.longitude, s.latitude, s.longitude) * 1000 as dist_m,
        row_number() over (
            partition by e.event_ref
            order by great_circle_distance(e.latitude, e.longitude, s.latitude, s.longitude)
        ) as rn
    from events e
    cross join stations s
),

station_pick as (
    select
        event_ref,
        max_by(station_name, rn = 1) as nearest_station_name,
        max_by(route, rn = 1) as nearest_station_route,
        round(min(dist_m)) as nearest_station_dist_m,
        count(case when dist_m <= 800 then 1 end) as stations_within_800m
    from station_dist
    where rn = 1 or dist_m <= 800
    group by event_ref
),

parking_dist as (
    select
        e.event_ref,
        p.parking_id,
        p.parking_name,
        great_circle_distance(e.latitude, e.longitude, p.latitude, p.longitude) * 1000 as dist_m,
        row_number() over (
            partition by e.event_ref
            order by great_circle_distance(e.latitude, e.longitude, p.latitude, p.longitude)
        ) as rn
    from events e
    cross join parkings p
),

parking_pick as (
    select
        event_ref,
        max_by(parking_id, rn = 1) as nearest_parking_id,
        max_by(parking_name, rn = 1) as nearest_parking_name,
        round(min(dist_m)) as nearest_parking_dist_m,
        count(case when dist_m <= 500 then 1 end) as parkings_within_500m
    from parking_dist
    where rn = 1 or dist_m <= 500
    group by event_ref
),

-- 최근접 주차장 × 행사 시각 칸의 평시 만차 확률(전 요일 평균 — 기간형 행사 근사).
parking_profile_at_evt as (
    select
        e.event_ref,
        avg(pf.full_prob) as nearest_parking_full_prob,
        sum(pf.base_n) as nearest_parking_profile_base_n
    from events e
    join parking_pick pp on e.event_ref = pp.event_ref
    join {{ ref('gold_transit_parking_profile') }} pf
        on pf.parking_id = pp.nearest_parking_id
       and pf.hh = e.evt_hh
    group by e.event_ref
)

select
    e.event_ref,
    e.event_type,
    e.title,
    e.venue_name,
    e.event_start_date,
    e.event_end_date,
    e.event_at,
    e.evt_hh,
    e.is_evt_hh_imputed,
    e.admin_dong_code,
    e.gu,
    e.latitude,
    e.longitude,
    -- 지하철 접근성(마스터 기반 — 전 행사 제공)
    sp.nearest_station_name,
    sp.nearest_station_route,
    sp.nearest_station_dist_m,
    sp.stations_within_800m,
    -- 주차 접근성
    pp.nearest_parking_id,
    pp.nearest_parking_name,
    pp.nearest_parking_dist_m,
    pp.parkings_within_500m,
    -- 행사 시간대 평시 만차 확률(전 요일 평균, evt_hh 미상은 19시 근사 — null=정보 없음)
    pr.nearest_parking_full_prob,
    pr.nearest_parking_profile_base_n
from events e
left join station_pick sp on e.event_ref = sp.event_ref
left join parking_pick pp on e.event_ref = pp.event_ref
left join parking_profile_at_evt pr on e.event_ref = pr.event_ref
