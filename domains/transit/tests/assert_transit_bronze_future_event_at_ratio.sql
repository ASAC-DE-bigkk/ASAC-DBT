-- #66: bronze 원천의 '미래 event_at' 비율을 감시하는 warn 테스트 (최근 윈도).
--   목적: silver 상한 필터가 '조용한 대량 드랍'을 하지 않는지(원천 시각체계 급변·대량 오염)
--   사람이 인지하게 한다. error 가 아니라 warn 인 이유: 미래 행 자체는 silver 에서 이미 안전히
--   제거되므로(assert_silver_transit_no_future_event_at 가 error 로 보증) 파이프를 멈출 사안은
--   아니고, '얼마나 버려지는가'를 관측·경보하는 감시 지표이기 때문.
--
--   윈도(#66 리뷰): 전 이력 비율은 이력이 쌓일수록 급성 이상(예: 원천 시계 붕괴로 당일
--   100% 미래)을 임계 아래로 희석하고, 매 빌드 전량 재파싱 비용도 무한 성장한다 —
--   ingested_at 기준 최근 var transit_freshness_monitor_hours(기본 24h)만 잰다.
--   윈도화로 파싱량이 상수화되어 bus_position(XML unnest)도 포함 가능해졌다.
--
--   대상: 3종 전부. event_at 도출식은 silver 모델과 동일 매크로
--   (transit_subway_event_at / transit_parking_event_at / transit_bus_*) 를 공유 —
--   silver 도출식이 바뀌면 모니터도 자동으로 같은 것을 잰다.
--
--   임계 var transit_freshness_warn_ratio(기본 5%): 배경상 subway_arrival 막차 잔존 quirk 는
--   소수 행 수준(실측 ~0.2%). 이를 크게 넘으면 원천 이상 신호.
--   잔여 한계: per-device 클럭 드리프트(개별 주차장 단말·버스 차량 몇 대만 +스큐 초과)는
--   원천 단위 비율 임계 아래로 소멸할 수 있다 — 이 테스트는 '원천 전체의 급성 이상' 감지용이며
--   소수 단말 드랍은 임계를 못 넘는다(개별 행은 silver 필터로 안전히 제거됨은 동일).
{{ config(severity='warn', tags=['hourly']) }}

{% set window_start -%}
cast(at_timezone(current_timestamp, 'UTC') as timestamp(6)) - interval '{{ var("transit_freshness_monitor_hours") }}' hour
{%- endset %}

with subway as (
    select
        {{ transit_subway_event_at('raw') }} as event_at,
        ingested_at
    from {{ source('transit_bronze', 'subway_arrival') }}
    where ingested_at >= {{ window_start }}
),

parking as (
    select
        {{ transit_parking_event_at('raw') }} as event_at,
        ingested_at
    from {{ source('transit_bronze', 'parking') }}
    where ingested_at >= {{ window_start }}
),

bus as (
    select
        {{ transit_bus_event_at(transit_bus_data_tm('item')) }} as event_at,
        b.ingested_at
    from {{ source('transit_bronze', 'bus_position') }} b
    cross join unnest({{ transit_bus_position_items('b.raw') }}) as t(item)
    where b.ingested_at >= {{ window_start }}
),

counts as (
    select
        'subway_arrival' as source,
        count_if({{ transit_event_at_is_future('event_at', 'ingested_at') }}) as future_rows,
        count(*) as total_rows
    from subway
    union all
    select
        'parking' as source,
        count_if({{ transit_event_at_is_future('event_at', 'ingested_at') }}) as future_rows,
        count(*) as total_rows
    from parking
    union all
    select
        'bus_position' as source,
        count_if({{ transit_event_at_is_future('event_at', 'ingested_at') }}) as future_rows,
        count(*) as total_rows
    from bus
),

-- 비율은 여기서 1회만 계산(SELECT/WHERE 중복 제거 — #66 리뷰).
ratios as (
    select
        source,
        future_rows,
        total_rows,
        future_rows * 1.0 / nullif(total_rows, 0) as future_ratio
    from counts
)

select source, future_rows, total_rows, future_ratio
from ratios
where future_ratio > {{ var('transit_freshness_warn_ratio') }}
