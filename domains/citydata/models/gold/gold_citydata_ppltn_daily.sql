-- gold(일자별): silver를 소비해 **장소별 하루 혼잡 인사이트**를 만든다.
-- "이 장소, 이 날: 평균 얼마나 붐볐고 / 언제 최고였고 / 붐빈 비율은?" 를 답한다.
-- grain = (event_date, area_code). 시간대별(gold_citydata_ppltn_by_time)의 일 단위 롤업.
--
-- 공간축: silver는 코드·좌표(area_cd·admin_dong_code·gu_code·lon·lat)만 담고, 이름
-- (area_nm/gu/admin_dong 등)은 dim_seoul_area 조인으로 붙인다(#115 정규화).
-- incremental(delete+insert): 최근 2일치만 재집계(그 날짜 전체 슬라이스로 완전 집계) 후
-- (event_date, area_code) 키로 delete+insert. 오늘 값은 슬라이스가 쌓일수록 갱신된다.

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", target.schema),
) }}

with base as (
    select
        cast(event_at as date) as event_date,
        area_cd,
        gu_code,
        admin_dong_code,
        longitude,
        latitude,
        area_congest_lvl,
        area_ppltn_min,
        area_ppltn_max,
        (area_ppltn_min + area_ppltn_max) / 2 as avg_pop,
        event_at
    from {{ ref('silver_citydata_ppltn') }}
    where event_at is not null
    {% if is_incremental() %}
    -- 최근 2일 수집분만 → 해당 날짜 전체를 재집계
    and collected_at >= current_timestamp - interval '2' day
    {% endif %}
),

agg as (
    select
        event_date,
        area_cd,
        max(gu_code) as gu_code,               -- area 당 상수
        max(admin_dong_code) as admin_dong_code,
        max(longitude) as longitude,
        max(latitude) as latitude,
        round(avg(avg_pop)) as average_population,   -- 일 평균 추정 인구
        max(area_ppltn_max) as max_population,       -- 일 최대
        min(area_ppltn_min) as min_population,       -- 일 최소
        max_by(event_at, avg_pop) as peak_at,        -- 가장 혼잡했던 시각(KST)
        max_by(area_congest_lvl, avg_pop) as peak_congestion_level,
        round(count_if(area_congest_lvl in ('붐빔', '약간 붐빔')) * 100.0 / count(*), 1)
            as busy_ratio_percent,                   -- 붐빔/약간붐빔 이었던 슬라이스 비율
        count(*) as measurement_count                -- 그날 수집 슬라이스 수(완결성)
    from base
    group by event_date, area_cd
)

select
    a.event_date,
    a.area_cd as area_code,
    dim.area_nm as area_name,
    dim.area_category as area_type,
    dim.sido,
    dim.gu,
    dim.admin_dong,
    a.gu_code,
    a.admin_dong_code,
    a.longitude,
    a.latitude,
    a.average_population,
    a.max_population,
    a.min_population,
    a.peak_at,
    a.peak_congestion_level,
    a.busy_ratio_percent,
    a.measurement_count
from agg a
left join {{ ref('dim_seoul_area') }} dim on a.area_cd = dim.area_cd
