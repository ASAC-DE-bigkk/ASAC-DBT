-- gold: 인구혼잡 이상탐지. grain = area_cd (장소당 현재 1행).
--
-- "지금 이 장소가 평소 같은 요일·시간대보다 얼마나 더/덜 붐비나" — 챗봇 "지금 평소보다
-- 붐벼?" / 사고·행사 이례 급증 자동 신호용. baseline = (장소×요일×시간) 과거 평균±표준편차,
-- 현재 = 최신 관측. z-score·% 편차로 이례성 정량화.
--
-- by_time 파생 table (조회 시 최신 baseline·현재 재계산 → 항상 라이브). 챗봇/API가 area_cd
-- 로 1행 읽어 바로 답변.

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", "seoul_citydata"),
) }}

with src as (
    select
        area_cd, area_nm, gu, gu_code, admin_dong, admin_dong_code,
        event_at, avg_ppltn, area_congest_lvl,
        hour(event_at) as hr,
        -- 2주 데이터라 요일 7분할은 표본이 얇음 → 주중/주말 2분할 (Sat=6, Sun=7)
        (day_of_week(event_at) >= 6) as is_weekend
    from {{ ref('gold_citydata_ppltn_by_time') }}
    where avg_ppltn is not null
),

-- 장소×주말여부×시간대 과거 baseline (평균·표준편차·표본수)
baseline as (
    select
        area_cd, is_weekend, hr,
        avg(avg_ppltn) as base_mean,
        stddev(avg_ppltn) as base_std,
        count(*) as base_n
    from src
    group by 1, 2, 3
),

-- 장소별 최신 관측
latest as (
    select *,
        row_number() over (partition by area_cd order by event_at desc) as rn
    from src
)

select
    l.area_cd,
    l.area_nm,
    l.gu,
    l.gu_code,
    l.admin_dong,
    l.admin_dong_code,
    l.event_at,
    l.is_weekend,
    l.hr,
    round(l.avg_ppltn, 0) as cur_ppltn,
    l.area_congest_lvl,
    round(b.base_mean, 0) as base_mean,
    round(l.avg_ppltn - b.base_mean, 0) as deviation,
    round((l.avg_ppltn - b.base_mean) / nullif(b.base_std, 0), 2) as z_score,
    round(l.avg_ppltn / nullif(b.base_mean, 0) - 1, 3) as pct_vs_normal,
    b.base_n
from latest l
join baseline b
    on b.area_cd = l.area_cd and b.is_weekend = l.is_weekend and b.hr = l.hr
where l.rn = 1
