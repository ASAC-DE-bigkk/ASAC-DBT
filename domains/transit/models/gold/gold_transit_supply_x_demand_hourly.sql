-- gold_transit_supply_x_demand_hourly — 수요 대비 공급 '교통 압박' (#291, G8, × citydata).
--
-- 한 행 = (area_cd, hour_at)의 수요(인구·승하차) vs 공급(주차 여유·운행 관측) 대조.
--   grain: (area_cd=핫스팟 121곳, hour_at). 사용자 화면: "성수카페거리: 인구 '붐빔'
--   + 주차 여유 5% → 지금 차 가져가면 안 됨".
--
-- ── citydata 기존 gold 와의 관계(#291 오픈 퀘스천) ──────────────────────
--   citydata 의 gold_citydata_ppltn_x_transit_hourly 는 동(dong) 축으로 인구×교통을
--   붙인다. 본 모델은 transit 기준 설계로 (1) 핫스팟(area_cd) 축 유지 — 사용자 카드가
--   '장소' 단위, (2) 승하차(수요)와 주차 여유(공급)의 대조 + 압박 플래그가 목적.
--   중복 정리 논의는 이슈 #291 에서 — 결과에 따라 통합·역할 분담 조정 가능.
--
-- ── 수요 축 ────────────────────────────────────────────────────────────
--   silver_citydata_ppltn: 시간 내 평균 인구((min+max)/2)·최신 혼잡 라벨.
--   silver_citydata_transit_ppltn: mode(bus/subway)별 5분 승차 인원((min+max)/2 평균).
--   버스 티어링(#440) 후 버스 위치 관측이 30분 주기라, 버스 '수요'는 이 5분 승하차가
--   핫스팟 한정으로 더 좋은 해상도를 준다(이슈 #291 계획).
--
-- ── 공급 축 ────────────────────────────────────────────────────────────
--   핫스팟의 admin_dong_code 로 gold_transit_dong_15min 시간 롤업을 조인:
--   주차 여유(1-점유율)·관측 lot 수·버스 관측 차량 수(전 티어 — 공급 커버리지 성격)·
--   지하철 도착 관측. 핫스팟 동에 주차 실측이 없으면 null = "정보 없음".
--
-- ── 압박 플래그 ─────────────────────────────────────────────────────────
--   is_parking_pressured = 혼잡 라벨('약간 붐빔'/'붐빔') AND 주차 점유 >= 0.8.
--   합성 지수(가중 공식)는 자의성이 커서 두지 않는다 — 구성 요소를 그대로 노출하고
--   판단 공식은 소비 측(대시보드)과 이슈 #291 에서 확정한다.
--
-- ── 증분(incremental merge) — 소스별 독립 임계 ─────────────────────────
--   unique_key=(area_cd, hour_at). 임계를 수요(citydata)·공급(transit) 축마다 따로
--   계산한다: 각 축이 실제로 채운 행의 max(hour_at) - 3h.
--   공유 임계를 쓰면 빠른 축이 프런티어를 밀어 올려, 느린 축의 backfill 이 필터에서
--   탈락하고 이미 쓰인 행의 그 축 컬럼이 영영 null 로 남는다(full_refresh=false 라
--   복구 불가). dev 에서 citydata 수집 중단(2026-07-17~20) 구간으로 실증됨.
--   citydata 보존 정책이 별도라 여기 merge 행이 핫스팟 수요-공급 쌍의 자체 아카이브.

-- ── Iceberg 일 파티셔닝 ────────────────────────────────────────────────
--   MERGE 가 대상 전체 데이터파일을 훑지 않고 최근 파티션만 건드리게 하고, 하위
--   소비(24h 창·프런티어 산출·시간 롤업)의 시간 술어가 프루닝된다. 테이블이 비어
--   있는 지금 넣지 않으면 full_refresh=false 라 나중엔 CTAS 백업→재적재 수동
--   절차를 거쳐야 바꿀 수 있다.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['area_cd', 'hour_at'],
    full_refresh=false,
    properties={'partitioning': "ARRAY['day(hour_at)']"},
) }}

{#- 아카이브 개시일 — 최초 빌드 하한이자, 축이 한 번도 랜딩되지 않았을 때의 fallback. -#}
{%- set archive_start = "timestamp '" ~ var("transit_archive_start_at") ~ "'" -%}

{%- set ppltn_threshold %}
{% if is_incremental() %}
(
    select coalesce(max(hour_at), {{ archive_start }}) - interval '3' hour
    from {{ this }}
    where ppltn_avg is not null
)
{% else %}{{ archive_start }}{% endif %}
{%- endset %}

{%- set boardings_threshold %}
{% if is_incremental() %}
(
    select coalesce(max(hour_at), {{ archive_start }}) - interval '3' hour
    from {{ this }}
    where bus_board_5min_avg is not null
       or subway_board_5min_avg is not null
)
{% else %}{{ archive_start }}{% endif %}
{%- endset %}

{%- set supply_threshold %}
{% if is_incremental() %}
(
    select coalesce(max(hour_at), {{ archive_start }}) - interval '3' hour
    from {{ this }}
    where parking_lot_cnt is not null
       or bus_veh_cnt is not null
       or subway_arrival_cnt is not null
)
{% else %}{{ archive_start }}{% endif %}
{%- endset %}

with ppltn as (
    select
        area_cd,
        date_trunc('hour', event_at) as hour_at,
        max(admin_dong_code) as admin_dong_code,
        max(gu_code) as gu_code,
        avg((area_ppltn_min + area_ppltn_max) / 2.0) as ppltn_avg,
        max((area_ppltn_min + area_ppltn_max) / 2.0) as ppltn_peak,
        max_by(area_congest_lvl, event_at) as congest_lvl_last,
        count(*) as ppltn_obs_cnt
    from {{ source('seoul_citydata', 'silver_citydata_ppltn') }}
    where event_at >= {{ ppltn_threshold }}
    group by 1, 2
),

boardings as (
    select
        area_cd,
        date_trunc('hour', observed_at) as hour_at,
        avg(case when mode = 'bus' then (gton_5min_min + gton_5min_max) / 2.0 end) as bus_board_5min_avg,
        avg(case when mode = 'bus' then (gtoff_5min_min + gtoff_5min_max) / 2.0 end) as bus_alight_5min_avg,
        avg(case when mode = 'subway' then (gton_5min_min + gton_5min_max) / 2.0 end) as subway_board_5min_avg,
        avg(case when mode = 'subway' then (gtoff_5min_min + gtoff_5min_max) / 2.0 end) as subway_alight_5min_avg,
        max(case when mode = 'subway' then station_count end) as subway_station_cnt
    from {{ source('seoul_citydata', 'silver_citydata_transit_ppltn') }}
    where observed_at >= {{ boardings_threshold }}
    group by 1, 2
),

supply as (
    select
        admin_dong_code,
        date_trunc('hour', bucket_at) as hour_at,
        avg(parking_occupancy_avg) as parking_occupancy_avg,
        max(parking_lot_cnt) as parking_lot_cnt,
        max(parking_full_lot_cnt) as parking_full_lot_cnt,
        max(bus_veh_cnt) as bus_veh_cnt,
        sum(subway_arrival_cnt) as subway_arrival_cnt
    from {{ ref('gold_transit_dong_15min') }}
    where bucket_at >= {{ supply_threshold }}
    group by 1, 2
)

select
    p.area_cd,
    p.admin_dong_code,
    p.gu_code,
    p.hour_at,
    -- 수요
    round(p.ppltn_avg, 1) as ppltn_avg,
    round(p.ppltn_peak, 1) as ppltn_peak,
    p.congest_lvl_last,
    b.bus_board_5min_avg,
    b.bus_alight_5min_avg,
    b.subway_board_5min_avg,
    b.subway_alight_5min_avg,
    b.subway_station_cnt,
    -- 공급(핫스팟 동 기준 — null = 해당 동 실측 없음)
    s.parking_occupancy_avg,
    case when s.parking_occupancy_avg is not null
         then round((1 - s.parking_occupancy_avg) * 100)
    end as parking_avail_pct,
    s.parking_lot_cnt,
    s.parking_full_lot_cnt,
    s.bus_veh_cnt,
    s.subway_arrival_cnt,
    -- 압박 플래그(구성 요소 기반 — 합성 지수 공식은 #291 논의)
    -- 주차 실측이 없는 동은 조건이 null → false 로 접는다(불리언 계약 유지).
    -- '압박 아님'과 '판단 불가'의 구분이 필요하면 parking_occupancy_avg 의 null 로 본다.
    coalesce(
        p.congest_lvl_last in ('약간 붐빔', '붐빔')
        and s.parking_occupancy_avg >= 0.8,
        false
    ) as is_parking_pressured
from ppltn p
left join boardings b
    on p.area_cd = b.area_cd and p.hour_at = b.hour_at
left join supply s
    on p.admin_dong_code = s.admin_dong_code and p.hour_at = s.hour_at
