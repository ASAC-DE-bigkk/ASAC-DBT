-- gold(Q&A metric): 장소 × 요일 × 시간 따릉이 가용 롤업. grain (area_cd, dow, hr).
--
-- "이 장소는 무슨 요일 몇 시에 따릉이가 많나/없나" — silver_citydata_sbike(대여소별 스냅샷
-- 시계열, observed_at=collected_at) 파생. 실시간 "지금 몇 대"(구 sbike_availability — PlayMCP
-- 실시간 MCP 가 커버) 대신 요일×시간 전형 패턴 = 우리 차별점(시계열 가치).
-- 수집 시점마다 영역 내 대여소를 합산(영역 총 가용대수) 후 요일×시간으로 평균.
--
-- ⚠ 표본 주의: base_n(셀 표본수)·reliable(base_n>=30) 동봉 — 소비측(챗봇/API)이 표본 적은
--   셀을 "참고용"으로 캐비앳. 데이터 누적되면 신뢰도 상승. table+replace(멱등).

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", target.schema),
    tags=['daily'],
) }}

with per_collection as (
    -- 수집 시점별 영역 집계 (대여소 합산 → 영역 총 가용/거치대)
    select
        area_cd,
        observed_at,
        sum(parking_count)       as bikes_avail,
        sum(rack_count)          as racks,
        day_of_week(observed_at) as dow,   -- 1=월 … 7=일
        hour(observed_at)        as hr     -- 0 … 23
    from {{ ref('silver_citydata_sbike') }}
    group by area_cd, observed_at
)

select
    p.area_cd,
    max(d.area_nm)         as area_nm,
    max(d.gu)              as gu,
    max(d.gu_code)         as gu_code,
    max(d.admin_dong)      as admin_dong,
    max(d.admin_dong_code) as admin_dong_code,
    max(d.area_category)   as area_category,
    p.dow,
    p.hr,
    cast(round(avg(p.bikes_avail), 0) as integer) as avg_bikes_available,
    cast(round(avg(p.racks), 0) as integer)       as avg_racks,
    cast(round(avg(case when p.racks > 0
                        then 100.0 * p.bikes_avail / p.racks end), 1) as double) as avg_availability_pct,
    count(*)         as base_n,
    (count(*) >= 30) as reliable
from per_collection p
left join {{ ref('dim_seoul_area') }} d on p.area_cd = d.area_cd
group by p.area_cd, p.dow, p.hr
