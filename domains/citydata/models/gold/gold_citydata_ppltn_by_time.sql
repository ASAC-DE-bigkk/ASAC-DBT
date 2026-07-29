-- gold(시간대별): silver를 소비해 시간대별 장소 인구혼잡도 + 평균 인구 파생.
--
-- 좌표(longitude/latitude)·행정구역(gu/admin_dong + 행안부 코드)·시간축(event_at)·분류는
-- 이미 silver에서 #48 공통축으로 보강되므로 여기서는 그대로 가져오고 파생(avg_ppltn)만
-- 계산한다. 실시간 지도(최신 슬라이스)와 시간별 분석(누적)용 마트. grain = (event_at, area_cd).

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", target.schema),
) }}

-- ⚠ silver가 incremental merge 과정에서 완전동일 중복행을 남길 수 있어(dbt-trino/Iceberg
-- merge가 update 대신 insert 하는 케이스 — 실패 run 재시도가 증폭), grain(event_at,
-- area_cd) 기준 1건으로 dedup한 뒤 merge한다. 이게 없으면 중복 소스가 gold merge의
-- MERGE_TARGET_ROW_MULTIPLE_MATCHES(한 target 행에 source 다수 매칭)를 유발한다.
with src as (
    select
        s.event_at,
        s.area_cd,
        s.gu_code,
        s.admin_dong_code,
        s.longitude,
        s.latitude,
        s.area_congest_lvl,
        s.area_ppltn_min,
        s.area_ppltn_max,
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
        s.collected_at,
        row_number() over (
            partition by s.event_at, s.area_cd order by s.collected_at desc
        ) as _rn
    from {{ ref('silver_citydata_ppltn') }} s
    {% if is_incremental() %}
    where s.collected_at >= (
        select coalesce(max(collected_at), timestamp '1970-01-01') - interval '30' minute
        from {{ this }}
    )
    {% endif %}
)

select
    s.event_at,
    dim.area_nm,
    s.area_cd,
    dim.sido,
    dim.gu,
    dim.admin_dong,
    s.gu_code,
    s.admin_dong_code,
    dim.area_category,
    s.longitude,
    s.latitude,
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
from src s
left join {{ ref('dim_seoul_area') }} dim on s.area_cd = dim.area_cd
where s._rn = 1
