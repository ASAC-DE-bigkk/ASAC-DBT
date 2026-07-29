-- gold(시간별): silver를 소비해 **장소별 시간 혼잡 인사이트**를 만든다.
-- "이 장소, 이 시간대: 평균 얼마나 붐볐고 / 언제 최고였고 / 붐빈 비율은?" 를 답한다.
-- grain = (time_bucket, area_cd). daily(일 롤업)와 by_time(5분) 사이의 시간 해상도 —
-- "지난 일주일 시간별" 서빙 조회를 채운다 (specs/2026-07-20).
--
-- 공간축: silver는 코드·좌표만 담고, 이름(area_nm/gu/admin_dong)은 dim_seoul_area 조인(#115).
-- 적재: table+replace (citydata 골드 불변식). D1 서빙은 export 단계에서 시간버킷 append.

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", target.schema),
) }}

with base as (
    select
        date_trunc('hour', event_at) as time_bucket,
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
),

agg as (
    select
        time_bucket,
        area_cd,
        max(gu_code) as gu_code,               -- area 당 상수
        max(admin_dong_code) as admin_dong_code,
        max(longitude) as longitude,
        max(latitude) as latitude,
        round(avg(avg_pop)) as average_population,   -- 시간 평균 추정 인구
        max(area_ppltn_max) as max_population,       -- 시간 최대
        min(area_ppltn_min) as min_population,       -- 시간 최소
        max_by(event_at, avg_pop) as peak_at,        -- 가장 혼잡했던 5분 시각(KST)
        max_by(area_congest_lvl, avg_pop) as peak_congestion_level,
        round(count_if(area_congest_lvl in ('붐빔', '약간 붐빔')) * 100.0 / count(*), 1)
            as busy_ratio_percent,                   -- 붐빔/약간붐빔 이었던 슬라이스 비율
        count(*) as measurement_count                -- 그 시간 수집 슬라이스 수(완결성, 최대 12)
    from base
    group by time_bucket, area_cd
)

select
    a.time_bucket,
    a.area_cd,
    dim.area_nm,
    dim.area_category,
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
