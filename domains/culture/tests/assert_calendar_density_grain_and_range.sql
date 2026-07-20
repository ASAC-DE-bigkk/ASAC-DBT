-- calendar_density 불변식(#269): 그레인(gu_code, event_date) 유일 + concentration 범위(0<c<=1)
--   + busiest_type_count <= total_events. 위반 행이 하나라도 있으면 실패.
with dupes as (
    select gu_code, event_date, count(*) as n
    from {{ ref('gold_culture_calendar_density') }}
    group by gu_code, event_date
    having count(*) > 1
),
bad_range as (
    select gu_code, event_date
    from {{ ref('gold_culture_calendar_density') }}
    where concentration <= 0 or concentration > 1
       or busiest_type_count > total_events
       or distinct_types < 1
)
select gu_code, event_date, 'dupe_grain' as violation from dupes
union all
select gu_code, event_date, 'bad_range' as violation from bad_range
