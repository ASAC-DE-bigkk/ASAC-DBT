-- gold(Q&A metric): 장소 × 요일 × 시간 인구혼잡 롤업. grain (area_cd, dow, hr).
--
-- "무슨 요일 몇 시가 붐비나/한산한가" — by_time 파생. forecast(주말/평일 2분할)의 요일 세분화판.
-- 해결 질문: "화요일 저녁 강남 붐빔?", "성수동 제일 한산한 요일·시간?".
--
-- ⚠ 표본 주의: 현재 데이터가 ~2.7주라 (area×dow×hr) 셀당 표본이 얇다(실측 median ~22, min ~9).
--   그래서 base_n(셀 표본수)·reliable(base_n>=30) 을 동봉해 소비측(챗봇/API)이 표본 적은 셀을
--   "참고용"으로 캐비앳하게 한다. forecast 가 요일 대신 주말/평일로 간 이유(표본 확보)를
--   이 골드는 base_n 노출로 대신 방어한다. 데이터 누적되면 신뢰도 상승 — 불필요 시 base_n 제거 가능
--   (table+replace 라 컬럼 삭제는 모델·contract·export 에서 한 줄씩 지우면 끝).

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", "seoul_citydata"),
) }}

with src as (
    select
        area_cd, area_nm, gu, gu_code, admin_dong, admin_dong_code, area_category,
        avg_ppltn, area_congest_lvl,
        day_of_week(event_at) as dow,   -- 1=월 … 7=일 (Trino day_of_week)
        hour(event_at)        as hr     -- 0 … 23
    from {{ ref('gold_citydata_ppltn_by_time') }}
    where avg_ppltn is not null
),

-- 셀별 최빈 혼잡도 (여유/보통/약간 붐빔/붐빔 중 최다)
lvl_counts as (
    select area_cd, dow, hr, area_congest_lvl, count(*) as n
    from src
    group by area_cd, dow, hr, area_congest_lvl
),
top_lvl as (
    select area_cd, dow, hr, max_by(area_congest_lvl, n) as typical_congest_lvl
    from lvl_counts
    group by area_cd, dow, hr
)

select
    s.area_cd,
    max(s.area_nm)          as area_nm,
    max(s.gu)               as gu,
    max(s.gu_code)          as gu_code,
    max(s.admin_dong)       as admin_dong,
    max(s.admin_dong_code)  as admin_dong_code,
    max(s.area_category)    as area_category,
    s.dow,
    s.hr,
    cast(round(avg(s.avg_ppltn), 0) as integer) as avg_ppltn,
    max(s.avg_ppltn)        as max_ppltn,
    min(s.avg_ppltn)        as min_ppltn,
    t.typical_congest_lvl,
    count(*)                as base_n,           -- 이 (장소·요일·시간) 셀의 표본 수
    (count(*) >= 30)        as reliable          -- 표본 충분 여부(초기엔 false 많음 — 소비측 캐비앳)
from src s
left join top_lvl t
    on t.area_cd = s.area_cd and t.dow = s.dow and t.hr = s.hr
group by s.area_cd, s.dow, s.hr, t.typical_congest_lvl
