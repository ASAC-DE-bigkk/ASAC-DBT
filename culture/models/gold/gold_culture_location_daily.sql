-- gold: culture 활동(공연 + 문화행사)을 자치구 × 일자로 집계. 다중 소스 union.
-- 각 활동의 구간(period_start~period_end)을 일자로 전개 → 혼잡 gold(자치구)와 시점 겹침 조인 가능.
-- 그레인: location_key(자치구) × event_date.

with activities as (
    -- KOPIS 공연
    select
        location_key,
        cast(performance_id as varchar) as activity_id,
        'performance'                   as activity_type,
        period_start,
        period_end
    from {{ ref('silver_culture_performance') }}
    where location_key is not null
      and period_start is not null
      and period_end is not null
      and period_end >= period_start
      and date_diff('day', period_start, period_end) <= 400

    union all

    -- 서울 문화행사
    select
        location_key,
        event_key  as activity_id,
        'event'    as activity_type,
        period_start,
        period_end
    from {{ ref('silver_culture_event') }}
    where location_key is not null
      and period_start is not null
      and period_end is not null
      and period_end >= period_start
      and date_diff('day', period_start, period_end) <= 400
),

expanded as (
    -- 구간 → 일자 전개: 각 활동이 활성인 모든 날짜로 펼친다.
    select
        a.location_key,
        a.activity_id,
        a.activity_type,
        d.activity_date
    from activities a
    cross join unnest(sequence(a.period_start, a.period_end, interval '1' day)) as d(activity_date)
)

select
    location_key,
    activity_date as event_date,                    -- 공용 date 키 (location_key × event_date 그레인)
    count(distinct activity_id) as activities_count,
    count(distinct case when activity_type = 'performance' then activity_id end) as performances_count,
    count(distinct case when activity_type = 'event' then activity_id end)       as events_count
from expanded
group by location_key, activity_date
