-- gold_transit_bus_route_timetable — 버스 노선 공표 시간표(첫차·막차·배차간격) 명부 (#510).
--
-- 한 행 = 버스 노선 1개(최신 주간 스냅샷). 원천은 bronze_bus_route_master 의
-- 시간표 필드(ASAC-DAG#765 — getBusRouteList 가 노선 단위로 제공, 원본 보존).
-- 페르소나 실측(ASK-Seoul#116)의 막차·배차 되물음을 직접 해소하는 축.
--
-- ── 시각 파싱 ────────────────────────────────────────────────────────────
--   first/last_bus_tm 은 API 가 '조회일+시각'(yyyyMMddHHmmss, 예 20260811043000)으로
--   준다 — 날짜부는 조회일일 뿐 의미가 없어 시각(HH:MM)만 취한다. 14자리가 아니면
--   (공백·결측) NULL. 막차가 자정 넘는 노선은 last < first 로 보인다 — 정렬·비교
--   소비자는 caveat 참조.
--
-- ── 스냅샷 선택 ──────────────────────────────────────────────────────────
--   마스터는 load_date 단위 멱등 적재 — dim_transit_bus_route_tier 와 동일하게
--   max(load_date)만 취한다(이번 주 실패 시 마지막 성공분 유지).
--
--   dong_now 류 실시간 모델이 아니고 주간 정적 명부라 table 물화(재계산 1.4k 행).

{{ config(materialized='table') }}

with latest_load as (
    select max(load_date) as load_date
    from {{ source('transit_bronze', 'bus_route_master') }}
),

master as (
    select m.*
    from {{ source('transit_bronze', 'bus_route_master') }} m
    join latest_load l on m.load_date = l.load_date
),

parsed as (
    select
        cast(bus_route_id as varchar)                        as bus_route_id,
        cast(bus_route_nm as varchar)                        as bus_route_nm,
        cast(route_type as varchar)                          as route_type,
        cast(tier as integer)                                as tier,
        -- routeType 7(인천)·8(경기)은 수도권 광역 노선 — 서울 시내 여부 구분 플래그
        (route_type not in ('7', '8'))                       as is_seoul_route,
        case when regexp_like(trim(first_bus_tm), '^\d{14}$')
             then substr(trim(first_bus_tm), 9, 2) || ':' || substr(trim(first_bus_tm), 11, 2)
        end                                                  as first_bus_time,
        case when regexp_like(trim(last_bus_tm), '^\d{14}$')
             then substr(trim(last_bus_tm), 9, 2) || ':' || substr(trim(last_bus_tm), 11, 2)
        end                                                  as last_bus_time,
        -- try(cast(nullif(...))) 는 이 Trino 버전에서 Bind→Lambda 내부 오류를 밟는다
        -- (2026-08-11 실측) — regexp 가드로 우회.
        case when regexp_like(trim(term), '^\d+$')
             then cast(trim(term) as integer)
        end                                                  as headway_min,
        nullif(trim(start_station_nm), '')                   as start_station_nm,
        nullif(trim(end_station_nm), '')                     as end_station_nm,
        nullif(trim(corp_nm), '')                            as corp_nm,
        cast(load_date as varchar)                           as snapshot_load_date,
        cast(collected_at as timestamp(6))                   as collected_at
    from master
)

select * from parsed
