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
-- ── 증분(incremental merge) — 소스별 독립 임계 ─────────────────────────
--   unique_key=(admin_dong_code, hour_at). 임계를 **소스마다 따로** 계산한다:
--   각 소스가 실제로 채운 행(sbike_spot_cnt / parking_lot_cnt·subway_arrival_cnt)의
--   max(hour_at) - 3h.
--
--   공유 임계(테이블 전체 max(hour_at))를 쓰면 안 되는 이유: 두 소스의 지연이 다르다.
--   빠른 쪽이 프런티어를 밀어 올리면, 느린 쪽이 나중에 그 이전 시각을 backfill 해도
--   `>= 임계` 필터에서 탈락해 union 전에 버려진다 → 이미 쓰인 행의 그 소스 컬럼이
--   영영 null 로 남는다(full_refresh=false 라 복구 불가). dev 에서 citydata 수집이
--   2026-07-17~20 멈춘 동안 transit 만 프런티어를 전진시킨 사례로 실증됨.
--
--   citydata 의 보존 정책이 별도라 여기 merge 로 남긴 행이 따릉이 이력의 자체 아카이브다.

-- ── Iceberg 일 파티셔닝 ────────────────────────────────────────────────
--   MERGE 가 대상 전체 데이터파일을 훑지 않고 최근 파티션만 건드리게 하고, 하위
--   소비(24h 창·프런티어 산출·시간 롤업)의 시간 술어가 프루닝된다. 테이블이 비어
--   있는 지금 넣지 않으면 full_refresh=false 라 나중엔 CTAS 백업→재적재 수동
--   절차를 거쳐야 바꿀 수 있다.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['admin_dong_code', 'hour_at'],
    full_refresh=false,
    properties={'partitioning': "ARRAY['day(hour_at)']"},
) }}

{#- 아카이브 개시일 — 최초 빌드 하한이자, 소스가 한 번도 랜딩되지 않았을 때의 fallback. -#}
{%- set archive_start = "timestamp '" ~ var("transit_archive_start_at") ~ "'" -%}

{%- set sbike_threshold %}
{% if is_incremental() %}
(
    select coalesce(max(hour_at), {{ archive_start }}) - interval '3' hour
    from {{ this }}
    where sbike_spot_cnt is not null
)
{% else %}{{ archive_start }}{% endif %}
{%- endset %}

{%- set transit_threshold %}
{% if is_incremental() %}
(
    select coalesce(max(hour_at), {{ archive_start }}) - interval '3' hour
    from {{ this }}
    where parking_lot_cnt is not null
       or subway_arrival_cnt is not null
)
{% else %}{{ archive_start }}{% endif %}
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
      and observed_at >= {{ sbike_threshold }}
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
    where bucket_at >= {{ transit_threshold }}
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
