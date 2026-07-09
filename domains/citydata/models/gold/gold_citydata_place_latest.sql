-- gold: 장소별 최신 크로스 신호 스냅샷 (#69). grain = area_cd (장소당 1행).
--
-- #192 의 핵심 가치 실현 — 같은 장소의 **혼잡도(silver_seoul_ppltn) × 소비 × 승하차 ×
-- 따릉이 × 대기질**을 최신 1행으로 붙인 실시간 지도/현황판 마트.
--
-- incremental(merge, key=area_cd): 최근 6시간 창에서 신호별 최신값을 뽑아 장소 단위로
-- merge — 창에 등장한 장소만 갱신되고 나머지는 직전 상태 유지. 전체 재생성이 없어
-- 스냅샷/파일 누적이 최소화된다. 재실행해도 같은 최신값으로 수렴(멱등).
-- (모든 신호가 5~10분 주기라 6시간 창이면 수집이 살아있는 한 항상 포함된다 —
--  일부 신호만 창에 없으면 해당 컬럼이 null 로 갱신되는데, 이는 "그 신호가 6시간째
--  끊김"의 정직한 표현이다.)

-- ⚠ 단일키(area_cd) merge 는 dbt-trino/Iceberg 에서 update 대신 중복 insert 하는
-- 케이스가 있어(라이브 incremental 에서 area_cd 당 N행 누적 → unique 테스트 실패),
-- **delete+insert** 로 한다: 매 run 창에 등장한 area_cd 를 지우고 다시 넣어 유일성 보장.
{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", "seoul_citydata"),
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['area_cd'],
    on_table_exists='drop',
) }}

{% set lookback = "timestamp '1970-01-01'" %}
{% if is_incremental() %}
    {% set lookback = "(select coalesce(max(refreshed_at), timestamp '1970-01-01') - interval '6' hour from " ~ this ~ ")" %}
{% endif %}

with ppltn as (
    select area_cd, area_congest_lvl, area_ppltn_min, area_ppltn_max, event_at as ppltn_at
    from (
        select *, row_number() over (partition by area_cd order by event_at desc) as rn
        from {{ ref('silver_seoul_ppltn') }}
        where event_at >= {{ lookback }}
    ) where rn = 1
),

cmrcl as (
    select area_cd, cmrcl_lvl, payment_count, payment_amt_min, payment_amt_max, event_at as cmrcl_at
    from (
        select *, row_number() over (partition by area_cd order by event_at desc) as rn
        from {{ ref('silver_citydata_cmrcl') }}
        where event_at >= {{ lookback }}
    ) where rn = 1
),

transit as (
    select
        area_cd,
        max(case when mode = 'subway' then gton_30min_max end) as subway_gton_30min,
        max(case when mode = 'bus' then gton_30min_max end) as bus_gton_30min,
        max(observed_at) as transit_at
    from (
        select *, row_number() over (partition by area_cd, mode order by observed_at desc) as rn
        from {{ ref('silver_citydata_transit_ppltn') }}
        where observed_at >= {{ lookback }}
    )
    where rn = 1
    group by area_cd
),

sbike as (
    -- 장소별 최신 관측시각의 대여소 합계 (가용 자전거·거치대)
    select area_cd, sum(parking_count) as sbike_parking_total,
           sum(rack_count) as sbike_rack_total, count(*) as sbike_spot_count,
           max(observed_at) as sbike_at
    from (
        select *, row_number() over (partition by area_cd, spot_id order by observed_at desc) as rn
        from {{ ref('silver_citydata_sbike') }}
        where observed_at >= {{ lookback }}
    )
    where rn = 1
    group by area_cd
),

air as (
    select area_cd, temperature, pm25, pm25_index, pm10, pm10_index, air_idx, event_at as air_at
    from (
        select *, row_number() over (partition by area_cd order by event_at desc) as rn
        from {{ ref('silver_citydata_air') }}
        where event_at >= {{ lookback }}
    ) where rn = 1
),

-- 이번 창에 어떤 신호든 등장한 장소만 갱신 대상
touched as (
    select area_cd from ppltn
    union select area_cd from cmrcl
    union select area_cd from transit
    union select area_cd from sbike
    union select area_cd from air
)

select
    t.area_cd,
    a.area_nm,
    a.area_category,
    a.gu,
    a.admin_dong,
    a.gu_code,
    a.admin_dong_code,
    a.longitude,
    a.latitude,
    p.area_congest_lvl,
    p.area_ppltn_min,
    p.area_ppltn_max,
    p.ppltn_at,
    c.cmrcl_lvl,
    c.payment_count,
    c.payment_amt_min,
    c.payment_amt_max,
    c.cmrcl_at,
    tr.subway_gton_30min,
    tr.bus_gton_30min,
    tr.transit_at,
    sb.sbike_parking_total,
    sb.sbike_rack_total,
    sb.sbike_spot_count,
    sb.sbike_at,
    ai.temperature,
    ai.pm25, ai.pm25_index,
    ai.pm10, ai.pm10_index,
    ai.air_idx,
    ai.air_at,
    greatest(
        coalesce(p.ppltn_at, timestamp '1970-01-01'),
        coalesce(c.cmrcl_at, timestamp '1970-01-01'),
        coalesce(tr.transit_at, timestamp '1970-01-01'),
        coalesce(sb.sbike_at, timestamp '1970-01-01'),
        coalesce(ai.air_at, timestamp '1970-01-01')
    ) as refreshed_at
from touched t
left join {{ ref('dim_seoul_area') }} a on t.area_cd = a.area_cd
left join ppltn p on t.area_cd = p.area_cd
left join cmrcl c on t.area_cd = c.area_cd
left join transit tr on t.area_cd = tr.area_cd
left join sbike sb on t.area_cd = sb.area_cd
left join air ai on t.area_cd = ai.area_cd
