-- gold: 대기질(미세먼지) 실시간 추세. grain = area_cd (장소당 현재 1행).
--
-- "미세먼지 나아지고 있어? 어제보다?" — 최근 1시간 평균 통합대기지수 vs 그 이전 1시간의
-- 변화. 실시간 스냅샷(place_latest)만으론 못 답하는 시계열 질문 = 우리 차별점.
-- 통합대기지수(air_idx_value)는 **높을수록 나쁨** → 오르면 '악화', 내리면 '개선'.
--
-- silver_citydata_air 파생(air 는 by_time 없음). 측정 ~10분 주기라 6버킷=1시간 근사.
-- table + replace(조회 시 최신 1행). place_latest 와 달리 '추세'라 시계열이 있어야만 답.

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", "seoul_citydata"),
    materialized='table',
    on_table_exists='replace',
    tags=['hourly'],
) }}

with ranked as (
    select
        a.area_cd, d.area_nm, d.area_category, d.gu, d.gu_code, d.admin_dong, d.admin_dong_code,
        a.event_at, a.pm25, a.pm25_index, a.pm10, a.pm10_index, a.air_idx, a.air_idx_value,
        row_number() over (partition by a.area_cd order by a.event_at desc) as rn
    from {{ ref('silver_citydata_air') }} a
    left join {{ ref('dim_seoul_area') }} d on a.area_cd = d.area_cd
    where a.air_idx_value is not null
),

-- 최근 12버킷(≈2시간)을 1시간씩 둘로: 최근 1h(rn 1~6) vs 이전 1h(rn 7~12)
windows as (
    select
        area_cd,
        avg(if(rn <= 6, air_idx_value)) as last_1h,
        avg(if(rn > 6 and rn <= 12, air_idx_value)) as prev_1h,
        avg(if(rn <= 6, pm25)) as last_pm25,
        avg(if(rn > 6 and rn <= 12, pm25)) as prev_pm25
    from ranked
    where rn <= 12
    group by 1
)

select
    c.area_cd,
    c.area_nm,
    c.area_category,
    c.gu,
    c.gu_code,
    c.admin_dong,
    c.admin_dong_code,
    c.event_at,
    c.pm25,
    c.pm25_index,
    c.pm10,
    c.pm10_index,
    c.air_idx,
    c.air_idx_value,
    round(w.last_1h, 1) as air_idx_last_1h,
    round(w.prev_1h, 1) as air_idx_prev_1h,
    round(w.last_pm25, 0) as pm25_last_1h,
    round(w.prev_pm25, 0) as pm25_prev_1h,
    round(w.last_1h / nullif(w.prev_1h, 0) - 1, 3) as change_pct,
    -- 통합대기지수 상승 = 대기질 악화
    case
        when w.last_1h > w.prev_1h * 1.05 then '악화'
        when w.last_1h < w.prev_1h * 0.95 then '개선'
        else '유지'
    end as trend
from ranked c
join windows w on w.area_cd = c.area_cd
where c.rn = 1
