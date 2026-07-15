-- gold: 인구혼잡 예보(패턴). grain = (area_cd, is_weekend, hr).
--
-- "이번 주말 홍대 얼마나 붐벼?" / "평일 강남 저녁 붐빔?" — 장소×주말여부×시간대의 과거 평균
-- 붐빔(±표준편차). 미래 시점 예상 혼잡을 조회. anomaly 의 baseline 을 독립 골드로 노출한 것.
--
-- 2주 데이터라 요일 7분할 대신 주중/주말 2분할(표본 확보). by_time 파생 table. 챗봇 예보 조회용.

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", "seoul_citydata"),
) }}

with src as (
    select
        area_cd, area_nm, gu, gu_code, admin_dong, admin_dong_code,
        avg_ppltn,
        hour(event_at) as hr,
        (day_of_week(event_at) >= 6) as is_weekend
    from {{ ref('gold_citydata_ppltn_by_time') }}
    where avg_ppltn is not null
)

select
    area_cd,
    max(area_nm) as area_nm,
    max(gu) as gu,
    max(gu_code) as gu_code,
    max(admin_dong) as admin_dong,
    max(admin_dong_code) as admin_dong_code,
    is_weekend,
    hr,
    round(avg(avg_ppltn), 0) as expected_ppltn,
    round(stddev(avg_ppltn), 0) as ppltn_std,
    round(max(avg_ppltn), 0) as peak_ppltn,
    count(*) as base_n
from src
group by area_cd, is_weekend, hr
