-- gold: 시간대별 장소 인구혼잡도 (silver를 소비, 평균 인구 등 파생).
--
-- 지금은 table(전체 재생성). silver를 소비하는 얇은 파생이라 비용이 작다.
-- 위치(중심점/카테고리)는 seed(seoul_ppltn_area_geo)를 area_cd로 left join --
-- 폴리곤 WKT는 행마다 붙이기엔 무거워 seed에 남겨두고 필요할 때 직접 join한다.

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
