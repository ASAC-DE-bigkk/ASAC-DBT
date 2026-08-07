-- gold(Q&A metric): 장소 × 요일 × 시간 인구혼잡 롤업. grain (area_cd, dow, hr).
--
-- "무슨 요일 몇 시가 붐비나/한산한가" — 시간 골드 ppltn_hourly 파생.
-- 해결 질문: "화요일 저녁 강남 붐빔?", "성수동 제일 한산한 요일·시간?".
--
-- 소스 변경(#467, Trino 연산 절감): 예전엔 by_time(5분 원본)에서 뽑았으나, by_time 은
--   실시간 지도 폐지(#404) 후 이 모델만 먹이는 763K 짜리 fast(5분) 증분 중간 테이블이었다.
--   → 이미 시간버킷으로 집계된 시간 골드 ppltn_hourly(79K)를 재사용한다(gold→gold 계층 유지,
--   by_time 폐기·5분 증분 제거로 연산·스토리지 절감). 결과 grain·컬럼은 동일.
--
-- ⚠ 표본 주의: hourly 소스라 base_n = (area×dow×hr) 셀의 **시간 관측 수 ≈ 관측 주수**(5분 대비 작다).
--   reliable(base_n>=3 = 3주+ 관측)·base_n 을 동봉해 소비측(챗봇/API)이 표본 적은 셀을 "참고용"으로
--   캐비앳하게 한다. 데이터 누적되면 신뢰도 상승. typical_congest_lvl 은 ppltn_hourly 의
--   시간 peak 혼잡도(hour 내 최혼잡 5분 레벨)의 셀별 최빈값 — 원본 5분 전체 최빈 대비 약간 상향.
{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", target.schema),
) }}

with src as (
    select
        area_cd, area_nm, gu, gu_code, admin_dong, admin_dong_code, area_category,
        average_population       as avg_ppltn,
        peak_congestion_level    as area_congest_lvl,
        day_of_week(time_bucket) as dow,   -- 1=월 … 7=일 (Trino day_of_week)
        hour(time_bucket)        as hr     -- 0 … 23
    from {{ ref('gold_citydata_ppltn_hourly') }}
    where average_population is not null
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
    cast(max(s.avg_ppltn) as integer) as max_ppltn,   -- average_population 은 double(round됨) → 계약 integer 로 캐스팅
    cast(min(s.avg_ppltn) as integer) as min_ppltn,
    t.typical_congest_lvl,
    count(*)                as base_n,           -- 이 (장소·요일·시간) 셀의 시간 관측 수(≈관측 주수)
    (count(*) >= 3)         as reliable          -- 3주+ 관측이면 신뢰(hourly 소스 — 임계 조정)
from src s
left join top_lvl t
    on t.area_cd = s.area_cd and t.dow = s.dow and t.hr = s.hr
group by s.area_cd, s.dow, s.hr, t.typical_congest_lvl
