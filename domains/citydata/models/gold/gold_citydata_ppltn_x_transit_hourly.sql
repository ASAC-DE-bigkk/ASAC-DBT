-- gold: 인구혼잡 × 대중교통·주차 (크로스도메인). grain = (time_bucket=시간, admin_dong_code).
--
-- 우리 인구를 행정동×시간으로 롤업하고, 그 동·시간의 버스혼잡·지하철대기·주차점유율
-- (codingpoppy94 transit 골드)을 붙인다. 답: "붐비는데 버스 미어터지나 / 주차 자리 있나".
-- 챗봇 "강남 지금 주차 돼?" / "버스 혼잡해?" 용.
--
-- source 는 transit 도메인 공용 스키마(TRANSIT_SCHEMA=transit, ASAC-DBT#204 전환).
-- 조인축 admin_dong_code + 시간.

-- view: R2 delete+insert 비원자성 중복 재발 방지 위해 view 전환(물리 write 없음·항상 라이브).
{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", "seoul_citydata"),
    materialized='view',
) }}

with ppltn_dong as (
    select
        date_trunc('hour', event_at) as time_bucket,
        admin_dong_code,
        max(gu_code) as gu_code,
        avg((area_ppltn_min + area_ppltn_max) / 2.0) as ppltn_avg,
        max((area_ppltn_min + area_ppltn_max) / 2.0) as ppltn_peak,
        count(distinct area_cd) as hotspot_count
    from {{ ref('silver_citydata_ppltn') }}
    where admin_dong_code is not null
    {% if is_incremental() %}
      and event_at >= (
        select coalesce(max(time_bucket), timestamp '1970-01-01') - interval '2' hour from {{ this }}
    )
    {% endif %}
    group by 1, 2
),

transit as (
    select
        admin_dong_code, hour_at,
        bus_congestion_avg, bus_full_ratio, bus_stop_ratio,
        subway_arrival_cnt, subway_wait_avg_s,
        parking_lot_cnt, parking_occupancy_avg, parking_full_lot_cnt
    from {{ source('transit_dong', 'gold_transit_dong_hourly') }}
)

select
    p.time_bucket,
    p.admin_dong_code,
    m.admin_dong,
    p.gu_code,
    m.gu,
    p.hotspot_count,
    round(p.ppltn_avg, 1) as ppltn_avg,
    round(p.ppltn_peak, 1) as ppltn_peak,
    t.bus_congestion_avg,
    t.bus_full_ratio,
    t.subway_arrival_cnt,
    t.subway_wait_avg_s,
    t.parking_lot_cnt,
    t.parking_occupancy_avg,
    t.parking_full_lot_cnt
from ppltn_dong p
left join transit t
    on t.admin_dong_code = p.admin_dong_code and t.hour_at = p.time_bucket
left join {{ ref('asac_axes', 'dim_admin_dong') }} m
    on p.admin_dong_code = m.admin_dong_code
