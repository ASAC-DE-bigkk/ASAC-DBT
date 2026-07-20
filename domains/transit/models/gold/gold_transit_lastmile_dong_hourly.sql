-- gold_transit_lastmile_dong_hourly — 지하철 주변 따릉이 라스트마일 (#289, G9, × citydata).
--
-- 한 행 = 지하철역 보유 동 1개 × 1시간의 라스트마일 상태(따릉이 잔여·주차 여유·지하철 대기).
--   grain: (admin_dong_code, hour_at). 사용자 시나리오: "역에서 내려서 따릉이 탈까,
--   차 가지고 갈까" — 역이 있는 동으로 한정한다(dim_transit_station 의 동, ~400개).
--
-- ── 따릉이 축(citydata, 핫스팟 121곳 주변 한정) ─────────────────────────
--   silver_citydata_sbike 는 대여소(spot)×5분 스냅샷. 대여소 단위로 시간 평균을 먼저
--   접고(관측 잦은 spot 과대대표 방지 — 아카이브 3종의 lot 선접기와 같은 관례) 동으로
--   합산한다. 커버리지: citydata 핫스팟 주변 대여소만 → 역 보유 동 중 일부만 채워짐.
--   sbike_* null 인 역 동은 "따릉이 정보 없음"이지 "따릉이 없음"이 아니다.
--
-- ── 주차·지하철 축 ─────────────────────────────────────────────────────
--   gold_transit_dong_15min 시간 롤업. 지하철 대기는 실시간 6역(4개 동) 한정 — 대부분 null.
--
-- ── 증분(incremental merge) ─────────────────────────────────────────────
--   unique_key=(admin_dong_code, hour_at), 임계 = 프런티어 - 3h(#286 관례).
--   citydata 의 보존 정책이 별도라(실측: 수집 중단 구간 존재) 여기 merge 로 남긴
--   행이 곧 따릉이 이력의 자체 아카이브다 → full_refresh 가드.
--   프런티어는 양 소스 프런티어의 max — 한쪽 수집이 멈춰도 다른 쪽 갱신을 막지 않는다.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['admin_dong_code', 'hour_at'],
    full_refresh=false,
) }}

{%- set threshold %}
{% if is_incremental() %}
(
    select coalesce(max(hour_at), timestamp '1970-01-01') - interval '3' hour
    from {{ this }}
)
{% else %}
timestamp '1970-01-01'
{% endif %}
{%- endset %}

with station_dong as (
    select distinct admin_dong_code
    from {{ ref('dim_transit_station') }}
    where admin_dong_code is not null
),

-- 대여소 단위 선접기 → 동 합산.
sbike_spot as (
    select
        admin_dong_code,
        date_trunc('hour', observed_at) as hour_at,
        spot_id,
        avg(cast(parking_count as double)) as spot_bike_avg,
        max_by(parking_count, observed_at) as spot_bike_last,
        max(observed_at) as spot_last_observed_at
    from {{ source('seoul_citydata', 'silver_citydata_sbike') }}
    where admin_dong_code is not null
      and observed_at >= {{ threshold }}
    group by 1, 2, 3
),

sbike_dong as (
    select
        admin_dong_code,
        hour_at,
        count(*) as sbike_spot_cnt,
        round(sum(spot_bike_avg)) as sbike_bike_avg_sum,
        sum(spot_bike_last) as sbike_bike_last_sum,
        max(spot_last_observed_at) as sbike_last_observed_at
    from sbike_spot
    group by 1, 2
),

transit_hour as (
    select
        admin_dong_code,
        date_trunc('hour', bucket_at) as hour_at,
        avg(parking_occupancy_avg) as parking_occupancy_avg,
        max(parking_lot_cnt) as parking_lot_cnt,
        avg(subway_wait_avg_s) as subway_wait_avg_s,
        sum(subway_arrival_cnt) as subway_arrival_cnt
    from {{ ref('gold_transit_dong_15min') }}
    where bucket_at >= {{ threshold }}
    group by 1, 2
),

grain as (
    select admin_dong_code, hour_at from sbike_dong
    union
    select admin_dong_code, hour_at from transit_hour
)

select
    g.admin_dong_code,
    m.admin_dong,
    m.gu_code,
    m.gu,
    g.hour_at,
    -- 따릉이(핫스팟 주변 한정 — null=정보 없음)
    s.sbike_spot_cnt,
    s.sbike_bike_avg_sum,
    s.sbike_bike_last_sum,
    s.sbike_last_observed_at,
    -- 주차 대안
    t.parking_occupancy_avg,
    t.parking_lot_cnt,
    -- 지하철(실시간 6역 4개 동 한정)
    t.subway_wait_avg_s,
    t.subway_arrival_cnt
from grain g
join station_dong sd on g.admin_dong_code = sd.admin_dong_code
left join sbike_dong s
    on g.admin_dong_code = s.admin_dong_code and g.hour_at = s.hour_at
left join transit_hour t
    on g.admin_dong_code = t.admin_dong_code and g.hour_at = t.hour_at
left join {{ ref('asac_axes', 'dim_admin_dong') }} m
    on g.admin_dong_code = m.admin_dong_code
