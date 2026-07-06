-- gold(일자별): silver를 소비해 **장소별 하루 혼잡 인사이트**를 만든다.
-- "이 장소, 이 날: 평균 얼마나 붐볐고 / 언제 최고였고 / 붐빈 비율은?" 를 답한다.
-- grain = (date, area_code). 시간대별(gold_seoul_ppltn_by_time)의 일 단위 롤업.
--
-- incremental(merge): 최근 2일치만 재집계(그 날짜 전체 슬라이스로 완전 집계) 후
-- (date, area_code) 키로 merge. 오늘 값은 슬라이스가 쌓일수록 갱신된다.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['date', 'area_code'],
    on_table_exists='drop',
) }}

with base as (
    select
        cast(substr(ppltn_time, 1, 10) as date) as date,
        area_cd,
        area_nm,
        area_category,
        sido,
        sigungu,
        dong,
        center_lon,
        center_lat,
        area_congest_lvl,
        area_ppltn_min,
        area_ppltn_max,
        (area_ppltn_min + area_ppltn_max) / 2 as avg_pop,
        ppltn_time
    from {{ ref('silver_seoul_ppltn') }}
    where ppltn_time is not null
    {% if is_incremental() %}
    -- 최근 2일 수집분만 → 해당 날짜 전체를 재집계(merge가 그 날짜 행을 갱신)
    and collected_at >= current_timestamp - interval '2' day
    {% endif %}
)

select
    date,
    area_cd as area_code,
    area_nm as area_name,
    area_category as area_type,
    sido,
    sigungu,
    dong,
    center_lon,
    center_lat,
    -- 하루 혼잡 인사이트
    round(avg(avg_pop)) as average_population,          -- 일 평균 추정 인구
    max(area_ppltn_max) as max_population,              -- 일 최대
    min(area_ppltn_min) as min_population,              -- 일 최소
    max_by(ppltn_time, avg_pop) as peak_datetime,      -- 가장 혼잡했던 시각
    max_by(area_congest_lvl, avg_pop) as peak_congestion_level,
    round(count_if(area_congest_lvl in ('붐빔', '약간 붐빔')) * 100.0 / count(*), 1)
        as busy_ratio_percent,                          -- 붐빔/약간붐빔 이었던 슬라이스 비율
    count(*) as measurement_count                       -- 그날 수집 슬라이스 수(완결성)
from base
group by
    date, area_cd, area_nm, area_category,
    sido, sigungu, dong, center_lon, center_lat
