-- gold: 시간대별 장소 인구혼잡도 (silver를 소비, 평균 인구 등 파생).
--
-- incremental(merge): silver의 최근 수집분만(30분 lookback) 읽어 (ppltn_time, area_cd)
-- 키로 merge한다. 5분마다 전체 재생성하지 않으므로 스냅샷/데이터파일 누적이 최소화된다.
-- 실시간 지도(최신 슬라이스)와 시간별 분석(누적 히스토리)을 한 테이블로 동시에 만족한다.
-- 위치(중심점/카테고리)는 seed(seoul_ppltn_area_geo)를 area_cd로 left join --
-- 폴리곤 WKT는 행마다 붙이기엔 무거워 seed에 남겨두고 필요할 때 직접 join한다.
--
-- ⚠ 기존 table에서 전환 시 drop 없이 그대로 run하면 기존 테이블에 merge된다(안전).
--   drop 직후 run은 R2 카탈로그 eventual consistency로 실패할 수 있다(README 참고).

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['ppltn_time', 'area_cd'],
) }}

select
    s.ppltn_time,
    s.area_nm,
    s.area_cd,
    geo.category as area_category,
    geo.center_lon,
    geo.center_lat,
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
left join {{ ref('seoul_ppltn_area_geo') }} geo
    on s.area_cd = geo.area_cd
{% if is_incremental() %}
-- 이미 반영된 collected_at 이후(-30분 여유)의 silver만 스캔. merge가 기존 키를
-- 갱신하므로 lookback으로 같은 행을 다시 읽어도 결과는 동일(멱등).
where s.collected_at >= (
    select coalesce(max(collected_at), timestamp '1970-01-01') - interval '30' minute
    from {{ this }}
)
{% endif %}
