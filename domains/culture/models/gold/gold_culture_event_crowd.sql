-- gold(크로스도메인): 문화 행사가 열리는 자치구의 요일×시간대별 평시 혼잡 베이스라인(#276, v2 #282).
--   그레인: gu_code × day_of_week × hour_of_day. citydata gold(장소×시간 인구혼잡)를 source로 읽어
--   event_schedule 이 있는 gu 로 스코프. "그 행사 지역 무슨 요일 몇 시가 붐비나/한적한가".
--   v2(#282): 요일 축 추가 — 셀당 p50 66샘플 실측(희소<3 셀 0%)으로 통계적 성립 확인.
--   ⚠ ~120 핫스팟 한정 평시 베이스라인 — 특정 행사일 실측 lift 아님. 18일 이력 기반.

with crowd as (
    select
        gu_code,
        day_of_week(event_at)                       as day_of_week,
        hour(event_at)                              as hour_of_day,
        (area_ppltn_min + area_ppltn_max) / 2.0     as ppltn_mid,
        area_congest_lvl,
        -- 혼잡 레벨 서수화: 여유1·보통2·약간붐빔3·붐빔4
        case area_congest_lvl
            when '여유'      then 1
            when '보통'      then 2
            when '약간 붐빔' then 3
            when '붐빔'      then 4
        end                                         as congest_score
    from {{ source('citydata_gold', 'gold_citydata_ppltn_by_time') }}
    where gu_code is not null and area_congest_lvl is not null
),

-- 문화 행사가 실제 열리는 자치구 + 이름
event_gu as (
    select gu_code, max(gu) as gu
    from {{ ref('gold_culture_event_schedule') }}
    where gu_code is not null
    group by gu_code
),

-- (gu, dow, hour) × 레벨 빈도 → 모달 혼잡 레벨
lvl_counts as (
    select c.gu_code, c.day_of_week, c.hour_of_day, c.area_congest_lvl, count(*) as cnt
    from crowd c
    join event_gu e on e.gu_code = c.gu_code
    group by c.gu_code, c.day_of_week, c.hour_of_day, c.area_congest_lvl
),
typical as (
    select gu_code, day_of_week, hour_of_day, max_by(area_congest_lvl, cnt) as typical_congest
    from lvl_counts
    group by gu_code, day_of_week, hour_of_day
),

agg as (
    select
        c.gu_code,
        c.day_of_week,
        c.hour_of_day,
        avg(c.ppltn_mid)      as avg_ppltn,
        avg(c.congest_score)  as avg_congest_score,
        count(*)              as crowd_samples
    from crowd c
    join event_gu e on e.gu_code = c.gu_code
    group by c.gu_code, c.day_of_week, c.hour_of_day
)

select
    a.gu_code,
    e.gu,
    cast(a.day_of_week as integer)          as day_of_week,
    cast(a.hour_of_day as integer)          as hour_of_day,
    cast(round(a.avg_ppltn) as integer)     as avg_ppltn,
    round(a.avg_congest_score, 3)           as avg_congest_score,
    t.typical_congest,
    cast(a.crowd_samples as integer)        as crowd_samples
from agg a
join event_gu e on e.gu_code = a.gu_code
join typical t on t.gu_code = a.gu_code and t.day_of_week = a.day_of_week and t.hour_of_day = a.hour_of_day
