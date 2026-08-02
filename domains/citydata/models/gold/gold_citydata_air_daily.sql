-- gold: 장소 × 일자 대기질 시계열. grain (area_cd, event_date).
--
-- "이 동네 미세먼지 요즘 며칠 추이는?" — silver_citydata_air 파생(air 는 by_time 없어 silver 직접).
-- 실시간 대기질(PlayMCP 실시간 MCP 가 커버) 대신 일별 평균으로 추세를 본다 = 우리 차별점.
-- 대기질은 사람 스케줄이 아니라 날씨·계절이 좌우 → 요일×시간 평균보다 일별 실측 추이가 의미.
-- air_idx_value 는 통합대기지수(높을수록 나쁨). table+replace(멱등).

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", target.schema),
    tags=['daily'],
) }}

select
    a.area_cd,
    max(d.area_nm)         as area_nm,
    max(d.gu)              as gu,
    max(d.gu_code)         as gu_code,
    max(d.admin_dong)      as admin_dong,
    max(d.admin_dong_code) as admin_dong_code,
    max(d.area_category)   as area_category,
    cast(a.event_at as date) as event_date,
    cast(round(avg(a.pm10), 0) as integer) as avg_pm10,
    cast(round(avg(a.pm25), 0) as integer) as avg_pm25,
    max(a.pm10)            as max_pm10,
    max(a.pm25)            as max_pm25,
    cast(round(avg(a.air_idx_value), 1) as double) as avg_air_idx_value,
    count(*)              as base_n
from {{ ref('silver_citydata_air') }} a
left join {{ ref('dim_seoul_area') }} d on a.area_cd = d.area_cd
where a.air_idx_value is not null
group by a.area_cd, cast(a.event_at as date)
