-- gold(시간대별): silver를 소비해 시간대별 장소 인구혼잡도 + 평균 인구 파생.
--
-- 좌표(center_lon/lat)·행정구역(시/구/동)·분류는 이미 silver에서 보강되므로
-- 여기서는 그대로 가져오고 파생(avg_ppltn)만 계산한다. 실시간 지도(최신 슬라이스)와
-- 시간별 분석(누적)을 만족하는 시간대별 마트. grain = (ppltn_time, area_cd).

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['ppltn_time', 'area_cd'],
    on_table_exists='drop',
) }}

select
    s.ppltn_time,
    s.area_nm,
    s.area_cd,
    s.sido,
    s.sigungu,
    s.dong,
    s.area_category,
    s.center_lon,
    s.center_lat,
    s.area_congest_lvl,
    s.area_ppltn_min,
    s.area_ppltn_max,
    (s.area_ppltn_min + s.area_ppltn_max) / 2 as avg_ppltn,
    s.male_ppltn_rate,
    s.female_ppltn_rate,
    s.ppltn_rate_0,
    s.ppltn_rate_10,
    s.ppltn_rate_20,
    s.ppltn_rate_30,
    s.ppltn_rate_40,
    s.ppltn_rate_50,
    s.ppltn_rate_60,
    s.ppltn_rate_70,
    s.resnt_ppltn_rate,
    s.non_resnt_ppltn_rate,
    s.collected_at
from {{ ref('silver_seoul_ppltn') }} s
{% if is_incremental() %}
where s.collected_at >= (
    select coalesce(max(collected_at), timestamp '1970-01-01') - interval '30' minute
    from {{ this }}
)
{% endif %}
