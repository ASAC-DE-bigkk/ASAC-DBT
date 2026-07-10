-- gold(일자별): silver를 소비해 **장소별 하루 혼잡 인사이트**를 만든다.
-- "이 장소, 이 날: 평균 얼마나 붐볐고 / 언제 최고였고 / 붐빈 비율은?" 를 답한다.
-- grain = (event_date, area_code). 시간대별(gold_seoul_ppltn_by_time)의 일 단위 롤업.
--
-- #48 공통축: 날짜축 event_date(=event_at의 날짜), 공간축 gu/admin_dong + 행안부 코드.
-- incremental(merge): 최근 2일치만 재집계(그 날짜 전체 슬라이스로 완전 집계) 후
-- (event_date, area_code) 키로 merge. 오늘 값은 슬라이스가 쌓일수록 갱신된다.

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", "seoul_citydata"),
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['event_date', 'area_code'],
    on_table_exists='drop',
) }}

with base as (
    select
        cast(event_at as date) as event_date,
        area_cd,
        area_nm,
        area_category,
        sido,
        gu,
        admin_dong,
        gu_code,
        admin_dong_code,
        longitude,
        latitude,
        area_congest_lvl,
        area_ppltn_min,
        area_ppltn_max,
        (area_ppltn_min + area_ppltn_max) / 2 as avg_pop,
        event_at
    from {{ ref('silver_seoul_ppltn') }}
    where event_at is not null
    {% if is_incremental() %}
    -- 최근 2일 수집분만 → 해당 날짜 전체를 재집계(merge가 그 날짜 행을 갱신)
    and collected_at >= current_timestamp - interval '2' day
    {% endif %}
)

select
    event_date,
    area_cd as area_code,
    area_nm as area_name,
    area_category as area_type,
    sido,
    gu,
    admin_dong,
    gu_code,
    admin_dong_code,
    longitude,
    latitude,
    -- 하루 혼잡 인사이트
    round(avg(avg_pop)) as average_population,          -- 일 평균 추정 인구
    max(area_ppltn_max) as max_population,              -- 일 최대
    min(area_ppltn_min) as min_population,              -- 일 최소
    max_by(event_at, avg_pop) as peak_at,              -- 가장 혼잡했던 시각(KST)
    max_by(area_congest_lvl, avg_pop) as peak_congestion_level,
    round(count_if(area_congest_lvl in ('붐빔', '약간 붐빔')) * 100.0 / count(*), 1)
        as busy_ratio_percent,                          -- 붐빔/약간붐빔 이었던 슬라이스 비율
    count(*) as measurement_count                       -- 그날 수집 슬라이스 수(완결성)
from base
group by
    event_date, area_cd, area_nm, area_category,
    sido, gu, admin_dong, gu_code, admin_dong_code, longitude, latitude
