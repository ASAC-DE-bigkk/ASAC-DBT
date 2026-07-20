-- gold: 일×구 문화 밀도·경쟁 지수. int_culture_activity_days 재사용(location_daily 동일 원천).
--   시민 "볼 게 많은 날" = total_events, 주최자 "피해야 할 날" = concentration(같은 유형 집중).
--   그레인: gu_code × event_date. location_daily가 유형별 count면, 여기는 다양성·집중도 요약.

with activities as (
    select * from {{ ref('int_culture_activity_days') }}
    where gu_code is not null
),

by_type as (
    select
        gu_code,
        max(gu)                     as gu,
        activity_date               as event_date,
        activity_type,
        count(distinct activity_id) as type_count
    from activities
    group by gu_code, activity_date, activity_type
),

agg as (
    select
        gu_code,
        max(gu)                          as gu,
        event_date,
        sum(type_count)                  as total_events,
        count(*)                         as distinct_types,
        max(type_count)                  as busiest_type_count,
        max_by(activity_type, type_count) as busiest_type
    from by_type
    group by gu_code, event_date
)

select
    gu_code,
    gu,
    event_date,
    cast(total_events as integer)                     as total_events,
    cast(distinct_types as integer)                   as distinct_types,
    busiest_type,
    cast(busiest_type_count as integer)               as busiest_type_count,
    -- 경쟁 집중도: 최다 유형이 그날 전체에서 차지하는 비율(0~1, 1=한 유형 독점)
    cast(busiest_type_count as double) / total_events as concentration
from agg
