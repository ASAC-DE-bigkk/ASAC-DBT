-- gold(크로스도메인): 문화 행사가 열리는 자치구의 요일×시간대별 평시 혼잡 베이스라인(#276, v2 #282).
--   그레인: gu_code × day_of_week × hour_of_day. citydata gold(장소×시간 인구혼잡)를 source로 읽어
--   event_schedule 이 있는 gu 로 스코프. "그 행사 지역 무슨 요일 몇 시가 붐비나/한적한가".
--   v2(#282): 요일 축 추가 — 셀당 p50 66샘플 실측(희소<3 셀 0%)으로 통계적 성립 확인.
--   v2 fix: 구 이름은 citydata 쪽에서 취함 — event_schedule 은 gu(소스 라벨)·gu_code(좌표
--   canonical)가 행 단위로 어긋날 수 있어(라벨-좌표 불일치, assert_gu_label_vs_coord_mismatch
--   참조) v1의 max(gu)가 오표기를 뽑았음(11110에 '중랑구' 등). citydata 쌍은 불일치 0 실측.
--   ⚠ ~120 핫스팟 한정 평시 베이스라인 — 특정 행사일 실측 lift 아님. 18일 이력 기반.

-- 🔄 소스 전환 2026-08-08 (ASAC-DBT#467 대응) — `gold_citydata_ppltn_by_time` 이 삭제됐다.
--    citydata 가 "dow_hour 전용 미사용 중간 테이블"로 보고 지웠는데 이 모델이 쓰고 있었다
--    (culture 쪽 sources.yml 선언이라 citydata manifest 에서 안 보인다 — 도메인 간 사각지대).
--    되살리기를 요청하지 않았다: 그 테이블이 5분마다 전량 재빌드되던 바로 그 비용원이다.
--
--    ⚠️ **혼잡도의 뜻이 바뀐다.** 전에는 5분 관측 하나하나의 등급이었고, 지금은 시간 버킷의
--    **최고(peak) 등급**이다. 그래서 `typical_congest`·`avg_congest_score` 는 위로 쏠린다 —
--    "그 시간대에 가장 자주 나타난 **최고** 혼잡"으로 읽어야 한다. 제품 문구도 그렇게 고쳤다.
--    되돌릴 방법은 없다: 시간 집계본에 5분 분포가 남아 있지 않다.
--
--    🔑 대신 **표본 수의 뜻은 지켰다.** `measurement_count`(그 버킷이 담은 5분 관측 수)를
--    합하면 예전 `count(*)` 와 같은 축이다 — 안 그러면 `crowd_samples` 가 100배쯤 작아져
--    소비자가 신뢰도를 오판한다. 실측 801,715 관측 / 82,987 버킷(2026-07-01~08-08).
with crowd as (
    select
        gu_code,
        gu,
        day_of_week(time_bucket)                    as day_of_week,
        hour(time_bucket)                           as hour_of_day,
        average_population                          as ppltn_mid,
        peak_congestion_level                       as area_congest_lvl,
        measurement_count                           as obs_count,
        -- 혼잡 레벨 서수화: 여유1·보통2·약간붐빔3·붐빔4 (어휘는 전환 후에도 동일 — 실측 확인)
        case peak_congestion_level
            when '여유'      then 1
            when '보통'      then 2
            when '약간 붐빔' then 3
            when '붐빔'      then 4
        end                                         as congest_score
    from {{ source('citydata_gold', 'gold_citydata_ppltn_hourly') }}
    where gu_code is not null and peak_congestion_level is not null
),

-- 문화 행사가 실제 열리는 자치구(스코프 필터만 — 이름은 citydata 쪽이 정확)
event_gu as (
    select distinct gu_code
    from {{ ref('gold_culture_event_schedule') }}
    where gu_code is not null
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
        max(c.gu)             as gu,   -- citydata 쌍은 gu_code당 이름 1개(불일치 0 실측)
        c.day_of_week,
        c.hour_of_day,
        avg(c.ppltn_mid)      as avg_ppltn,
        avg(c.congest_score)  as avg_congest_score,
        -- 버킷 수가 아니라 **그 버킷들이 담은 5분 관측 수의 합**이다(위 주석 참조).
        sum(c.obs_count)      as crowd_samples
    from crowd c
    join event_gu e on e.gu_code = c.gu_code
    group by c.gu_code, c.day_of_week, c.hour_of_day
)

select
    a.gu_code,
    a.gu,
    cast(a.day_of_week as integer)          as day_of_week,
    cast(a.hour_of_day as integer)          as hour_of_day,
    cast(round(a.avg_ppltn) as integer)     as avg_ppltn,
    round(a.avg_congest_score, 3)           as avg_congest_score,
    t.typical_congest,
    cast(a.crowd_samples as integer)        as crowd_samples
from agg a
join typical t on t.gu_code = a.gu_code and t.day_of_week = a.day_of_week and t.hour_of_day = a.hour_of_day
