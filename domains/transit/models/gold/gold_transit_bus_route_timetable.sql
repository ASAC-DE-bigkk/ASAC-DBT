-- gold_transit_bus_route_timetable — 버스 노선 공표 시간표(첫차·막차·배차간격) 명부 (#510).
--
-- 한 행 = 버스 노선 1개(최신 주간 스냅샷). 원천은 bronze_bus_route_master 의
-- 시간표 필드(ASAC-DAG#765 — getBusRouteList 가 노선 단위로 제공, 원본 보존).
-- 페르소나 실측(ASK-Seoul#116)의 막차·배차 되물음을 직접 해소하는 축.
--
-- ── 시각 파싱 (#116 리뷰 반영) ──────────────────────────────────────────
--   first/last_bus_tm 은 yyyyMMddHHmmss. 날짜부의 절대값은 조회 시점·요일에
--   따라 흔들리므로 쓰지 않고, 같은 행 안의 상대 신호만 쓴다: 막차 날짜부가
--   첫차보다 뒤(자정 걸침, N61 23:40→익일 04:10)거나 막차가 05시 미만(전 운행이
--   익일 새벽, N26 00:00~03:25)이면 is_overnight_last_bus=true.
--   시각부 000000 은 first==last 쌍(term=0 동반)일 때만 공표 누락 플레이스홀더로
--   NULL 처리한다 — N26 의 진짜 자정 첫차(00:00)는 보존된다(실측).
--   14자리가 아니면(공백·결측) NULL. 막차 날짜부가 첫차보다 앞서는 원천 모순
--   행(실측 1건, 반디1)은 자정 걸침 아님으로 두고 값은 보존한다.
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

raw_parsed as (
    select
        cast(bus_route_id as varchar)                        as bus_route_id,
        cast(bus_route_nm as varchar)                        as bus_route_nm,
        cast(route_type as varchar)                          as route_type,
        cast(tier as integer)                                as tier,
        case when regexp_like(trim(first_bus_tm), '^\d{14}$')
             then trim(first_bus_tm) end                     as first_raw,
        case when regexp_like(trim(last_bus_tm), '^\d{14}$')
             then trim(last_bus_tm) end                      as last_raw,
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
),

parsed as (
    select
        bus_route_id,
        bus_route_nm,
        route_type,
        tier,
        -- routeType 7(인천)·8(경기)이 아니면 서울 시내 노선. 미상(NULL)은 tier
        -- 철학(명시적으로만 판정)에 맞춰 false — WHERE is_seoul_route 소비자에서
        -- NULL 로 조용히 새지 않게 명시한다(#116 리뷰).
        coalesce(route_type not in ('7', '8'), false)        as is_seoul_route,
        substr(first_raw, 1, 8)                              as first_date_raw,
        substr(last_raw, 1, 8)                               as last_date_raw,
        -- 플레이스홀더(공표 누락)는 first==last 인 000000 쌍(실측: term=0 동반).
        -- first 만 000000 이고 last 가 다른 값이면 진짜 자정 첫차(N26).
        case when first_raw is not null
              and not (substr(first_raw, 9, 6) = '000000'
                       and (last_raw is null or first_raw = last_raw))
             then substr(first_raw, 9, 2) || ':' || substr(first_raw, 11, 2)
        end                                                  as first_bus_time,
        case when last_raw is not null
              and (substr(last_raw, 9, 6) <> '000000'
                   or substr(last_raw, 1, 8) > substr(first_raw, 1, 8))
             then substr(last_raw, 9, 2) || ':' || substr(last_raw, 11, 2)
        end                                                  as last_bus_time,
        headway_min,
        start_station_nm,
        end_station_nm,
        corp_nm,
        snapshot_load_date,
        collected_at
    from raw_parsed
)

select
    bus_route_id,
    bus_route_nm,
    route_type,
    tier,
    is_seoul_route,
    -- 심야 막차 판정 — 모델 헤더 주석 참조(#116 리뷰).
    coalesce(
        last_bus_time is not null
        and (last_date_raw > first_date_raw or substr(last_bus_time, 1, 2) < '05'),
        false)                                               as is_overnight_last_bus,
    first_bus_time,
    last_bus_time,
    headway_min,
    start_station_nm,
    end_station_nm,
    corp_nm,
    snapshot_load_date,
    collected_at
from parsed
