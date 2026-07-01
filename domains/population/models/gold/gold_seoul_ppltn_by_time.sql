-- gold: 시간대별 장소 인구혼잡도 (silver를 소비, 평균 인구 등 파생).
--
-- 지금은 table(전체 재생성). silver를 소비하는 얇은 파생이라 비용이 작다.

select
    ppltn_time,
    area_nm,
    area_cd,
    area_congest_lvl,
    area_ppltn_min,
    area_ppltn_max,
    (area_ppltn_min + area_ppltn_max) / 2 as avg_ppltn,
    male_ppltn_rate,
    female_ppltn_rate,
    ppltn_rate_0,
    ppltn_rate_10,
    ppltn_rate_20,
    ppltn_rate_30,
    ppltn_rate_40,
    ppltn_rate_50,
    ppltn_rate_60,
    ppltn_rate_70,
    resnt_ppltn_rate,
    non_resnt_ppltn_rate,
    collected_at
from {{ ref('silver_seoul_ppltn') }}
