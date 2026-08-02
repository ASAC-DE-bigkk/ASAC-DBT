-- gold(Q&A metric): 장소 × 요일 × 시간 EV 충전소 가용 롤업. grain (area_cd, dow, hr).
--
-- "이 장소는 무슨 요일 몇 시에 충전소가 잘 비나" — silver_citydata_charger 파생.
-- 실시간 "지금 쓸 수 있나"(구 charger_availability — PlayMCP 실시간 MCP 커버 + ASAC-DBT#401
-- 제거)를 대신하는 요일×시간 전형 패턴 = 우리 차별점(시계열 가치).
--
-- ⚠ silver_charger 는 **상태변경 로그**(observed_at=STATUPDDT, 상태 안 바뀌면 새 행 없음).
--   naive 평균(행 기준)은 자주 바뀌는 충전기를 과대대표해 편향 → **as-of 시간 스파인 리샘플링**:
--   최근 3주 매시각에 각 충전기의 as-of 상태(그 시각을 포함하는 구간)를 구해 요일×시간으로 평균.
--   이러면 "2018년부터 계속 사용가능"인 충전기도 매 시각 '사용가능'으로 올바르게 반영된다.
--   charger 식별 = (area_cd, stat_id, charger_id). table+replace(멱등).

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", target.schema),
    tags=['daily'],
) }}

with states as (
    -- 충전기별 상태 구간 [observed_at, next_at). 활성(마지막) 상태는 먼 미래 sentinel.
    select
        area_cd, stat_id, charger_id, charger_stat,
        observed_at,
        coalesce(
            lead(observed_at) over (
                partition by area_cd, stat_id, charger_id order by observed_at),
            timestamp '2999-01-01 00:00:00'
        ) as next_at
    from {{ ref('silver_citydata_charger') }}
),

bounds as (select max(observed_at) as mx from states),

spine as (
    -- 최신 데이터 기준 최근 3주 시간 스파인 (요일×시간 표본 확보, tz 이슈 회피)
    select ts as hour_ts
    from bounds
    cross join unnest(sequence(
        date_trunc('hour', mx - interval '21' day),
        date_trunc('hour', mx),
        interval '1' hour
    )) as t(ts)
),

hourly as (
    -- 각 (충전기 × 스파인시각)의 as-of 상태 = 그 시각을 포함하는 구간
    select
        s.area_cd, s.stat_id, s.charger_id,
        s.charger_stat,
        day_of_week(sp.hour_ts) as dow,
        hour(sp.hour_ts)        as hr
    from states s
    join spine sp
        on sp.hour_ts >= date_trunc('hour', s.observed_at)
       and sp.hour_ts <  s.next_at
)

select
    h.area_cd,
    max(d.area_nm)         as area_nm,
    max(d.gu)              as gu,
    max(d.gu_code)         as gu_code,
    max(d.admin_dong)      as admin_dong,
    max(d.admin_dong_code) as admin_dong_code,
    max(d.area_category)   as area_category,
    h.dow,
    h.hr,
    cast(round(100.0 * avg(if(h.charger_stat = '사용가능', 1, 0)), 1) as double) as avg_available_pct,
    count(distinct h.stat_id || '|' || h.charger_id) as n_chargers,
    count(*)         as base_n,
    (count(*) >= 30) as reliable
from hourly h
left join {{ ref('dim_seoul_area') }} d on h.area_cd = d.area_cd
group by h.area_cd, h.dow, h.hr
