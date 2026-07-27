-- gold: 대기질(미세먼지) 이상탐지. grain = area_cd (장소당 현재 1행).
--
-- "지금 이 동네가 평소 같은 요일·시간대보다 공기가 얼마나 더 나쁜가" — 챗봇 "오늘 미세먼지
-- 평소보다 심해?" 신호용. baseline = (장소×주말여부×시간) 과거 평균±표준편차 통합대기지수,
-- 현재 = 최신 관측. z-score·% 편차로 이례성 정량화. 통합대기지수(air_idx_value)는 높을수록
-- 나쁨 → 양의 편차 = 평소보다 나쁨. 실시간 스냅샷만으론 못 하고 축적 시계열 baseline 이 있어야
-- 답하는 질문 = find_anomalies(붐빔)의 대기질 버전.
--
-- silver_citydata_air 파생(air 는 by_time 없음). table+replace(조회 시 최신 재계산 → 라이브).

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", "seoul_citydata"),
    tags=['hourly'],
) }}

with src as (
    select
        a.area_cd, d.area_nm, d.gu, d.gu_code, d.admin_dong, d.admin_dong_code,
        a.event_at, a.air_idx_value, a.air_idx, a.pm25, a.pm25_index, a.pm10, a.pm10_index,
        hour(a.event_at) as hr
    from {{ ref('silver_citydata_air') }} a
    left join {{ ref('dim_seoul_area') }} d on a.area_cd = d.area_cd
    where a.air_idx_value is not null
),

-- 장소×시간대 과거 baseline (통합대기지수 평균·표준편차·표본수).
-- 주말 split 은 제외 — air 는 주말효과가 작고, 15일 축적에선 (주말×시간) 셀이 표본 1~2개로
-- 붕괴(밤·주말 특히). (장소×시간)이면 시간당 수십 표본 확보. 데이터 더 쌓이면 주말 분할 검토.
baseline as (
    select
        area_cd, hr,
        avg(air_idx_value) as base_mean,
        stddev(air_idx_value) as base_std,
        count(*) as base_n
    from src
    group by 1, 2
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
    l.hr,
    l.pm25,
    l.pm25_index,
    l.pm10,
    l.pm10_index,
    l.air_idx,
    round(l.air_idx_value, 1) as cur_air_idx,
    round(b.base_mean, 1) as base_mean,
    round(l.air_idx_value - b.base_mean, 1) as deviation,
    round((l.air_idx_value - b.base_mean) / nullif(b.base_std, 0), 2) as z_score,
    round(l.air_idx_value / nullif(b.base_mean, 0) - 1, 3) as pct_vs_normal,
    -- 통합대기지수 상승 = 평소보다 나쁨
    case
        when l.air_idx_value > b.base_mean * 1.05 then '평소보다 나쁨'
        when l.air_idx_value < b.base_mean * 0.95 then '평소보다 좋음'
        else '평소 수준'
    end as vs_normal,
    b.base_n
from latest l
join baseline b
    on b.area_cd = l.area_cd and b.hr = l.hr
where l.rn = 1
