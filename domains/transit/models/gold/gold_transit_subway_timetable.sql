-- gold_transit_subway_timetable — 지하철 역별 첫차·막차·열차 수 요약 명부 (#512).
--
-- 한 행 = (역, 요일구분, 방향). 원천은 bronze_subway_timetable(OA-101 공표 시간표,
-- ASAC-DAG#766 월 전량·일 분할 수집). 페르소나 실측(ASK-Seoul#116) 첫차·막차
-- 되물음의 지하철 쪽 해소 축.
--
-- ── 운행 시각 축(#116 리뷰 반영) ────────────────────────────────────────
--   기점역 출발행은 ARRIVETIME='00:00:00' 이고 실제 시각이 LEFTTIME 에 있다
--   (2026-08-11 실측: 1,551행 중 204행 — 구파발·온수 등 기점역 첫차가 최대
--   39분 늦게 잡히던 원인). 따라서 시각 축은 "그 역의 열차 운행 시각" 으로
--   통일한다: ARRIVETIME 이 유효하면 도착, '00:00:00'(기점 출발행)이면 LEFTTIME.
--   둘 다 '00:00:00' 이면 시각 미상으로 제외.
--
-- ── 자정 넘는 막차 처리 ─────────────────────────────────────────────────
--   원천은 자정 이후를 24:MM·25:MM 로 표기한다(실측). 혹시 모를 00:xx~02:xx
--   표기도 +24h 보정한 정렬 키로 흡수해 min_by/max_by 를 뽑는다
--   (표기는 원본 HH:MM 유지 — caveat 에 명시).
--
-- ── cycle 선택 ──────────────────────────────────────────────────────────
--   최신 cycle(YYYY-MM)만 취한다. 월 순회가 진행 중이면 일부 역만 있을 수 있다
--   (커버리지가 수일에 걸쳐 차오름) — caveat 에 명시.

{{ config(materialized='table') }}

with latest_cycle as (
    select max(cycle_id) as cycle_id
    from {{ source('transit_bronze', 'subway_timetable') }}
),

rows_in_cycle as (
    select
        t.req_station_cd                                as station_cd,
        cast(t.req_week_tag as integer)                 as week_tag,
        cast(t.req_inout_tag as integer)                as inout_tag,
        nullif(trim(t.line_num), '')                    as line_num,
        nullif(trim(t.station_nm), '')                  as station_nm,
        -- 운행 시각: 도착 유효 시 도착, 기점 출발행('00:00:00')은 출발(LEFTTIME)
        case when nullif(trim(t.arrivetime), '') not in ('00:00:00')
             then trim(t.arrivetime)
             when nullif(trim(t.lefttime), '') not in ('00:00:00')
             then trim(t.lefttime)
        end                                             as arrive_time,
        nullif(trim(t.express_yn), '')                  as express_yn,
        t.cycle_id,
        t.collected_at
    from {{ source('transit_bronze', 'subway_timetable') }} t
    join latest_cycle l on t.cycle_id = l.cycle_id
),

timed as (
    select * from rows_in_cycle
    where arrive_time is not null                       -- 도착·출발 모두 미상인 행만 제외
),

keyed as (
    select
        *,
        -- 03:00 미만은 익일 연장으로 +24h 보정한 분 단위 정렬 키
        (cast(substr(arrive_time, 1, 2) as integer)
         + case when substr(arrive_time, 1, 2) < '03' then 24 else 0 end) * 60
        + cast(substr(arrive_time, 4, 2) as integer)    as arrive_key_min
    from timed
),

summarized as (
    select
        station_cd,
        week_tag,
        inout_tag,
        max(line_num)                                       as line_num,
        max(station_nm)                                     as station_nm,
        substr(min_by(arrive_time, arrive_key_min), 1, 5)   as first_train_time,
        substr(max_by(arrive_time, arrive_key_min), 1, 5)   as last_train_time,
        count(*)                                            as train_count,
        -- 급행 코드는 D 다(#116 리뷰 실측 — 9호선 D 정차역 16개 = 급행 정차역
        -- 명단과 일치, 3~8호선은 D 0건. G 는 일반). 초기 구현의 G 판정은 반전.
        count_if(express_yn = 'D')                          as express_train_count,
        max(cycle_id)                                       as cycle_id,
        max(collected_at)                                   as collected_at
    from keyed
    group by station_cd, week_tag, inout_tag
)

select
    s.*,
    d.route,
    d.gu_code,
    d.gu,
    d.admin_dong_code,
    d.admin_dong,
    d.latitude,
    d.longitude
from summarized s
left join {{ ref('dim_transit_station') }} d
  on s.station_cd = d.station_id
