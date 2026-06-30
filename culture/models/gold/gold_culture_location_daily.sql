-- gold: 공연 구간(period_start~period_end)을 일자로 전개해 location_key × date 집계.
-- location_key = 자치구(공연장→facility.gugunnm 매핑). 혼잡 gold(자치구 그레인)와 시점 겹침 조인 가능.
-- 그레인: location_key(자치구) × event_date.

with perf as (
    select
        location_key,
        performance_id,
        genre,
        period_start,
        period_end
    from {{ ref('silver_culture_performance') }}
    where location_key is not null
      and period_start is not null
      and period_end is not null
      and period_end >= period_start
      and date_diff('day', period_start, period_end) <= 400  -- 비정상 초장기 구간 가드
),

expanded as (
    -- 구간 → 일자 전개: 각 공연이 활성인 모든 날짜로 펼친다.
    select
        p.location_key,
        p.performance_id,
        p.genre,
        d.activity_date
    from perf p
    cross join unnest(sequence(p.period_start, p.period_end, interval '1' day)) as d(activity_date)
)

select
    location_key,
    activity_date as event_date,                 -- 공용 date 키 (location_key × event_date 그레인)
    count(distinct performance_id) as performances_count,
    count(distinct genre)          as genres_count
from expanded
group by location_key, activity_date
