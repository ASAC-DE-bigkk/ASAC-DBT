-- gold_transit_subway_timetable — 지하철 역별 첫차·막차·열차 수 요약 명부 (#512).
--
-- 한 행 = (역, 요일구분, 방향). 원천은 bronze_subway_timetable(OA-101 공표 시간표,
-- ASAC-DAG#766 월 전량·일 분할 수집). 페르소나 실측(ASK-Seoul#116) 첫차·막차
-- 되물음의 지하철 쪽 해소 축.
--
-- ── 자정 넘는 막차 처리 ─────────────────────────────────────────────────
--   ARRIVETIME '00:xx'~'02:xx' 는 전날 운행의 연장(심야)이다 — 문자열 min/max 로
--   잡으면 00:10 이 '첫차'가 된다. 03:00 미만은 +24h 로 보정한 정렬 키로
--   min_by/max_by 를 뽑는다(표기는 원본 HH:MM 유지 — caveat 에 명시).
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
        nullif(trim(t.arrivetime), '')                  as arrive_time,
        nullif(trim(t.express_yn), '')                  as express_yn,
        t.cycle_id,
        t.collected_at
    from {{ source('transit_bronze', 'subway_timetable') }} t
    join latest_cycle l on t.cycle_id = l.cycle_id
    where nullif(trim(t.arrivetime), '') is not null
      and trim(t.arrivetime) <> '00:00:00'              -- 시각 미상 행(막차 아님) 제외
),

keyed as (
    select
        *,
        -- 03:00 미만은 익일 연장으로 +24h 보정한 분 단위 정렬 키
        (cast(substr(arrive_time, 1, 2) as integer)
         + case when substr(arrive_time, 1, 2) < '03' then 24 else 0 end) * 60
        + cast(substr(arrive_time, 4, 2) as integer)    as arrive_key_min
    from rows_in_cycle
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
        count_if(express_yn = 'G')                          as express_train_count,
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
