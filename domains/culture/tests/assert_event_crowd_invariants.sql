-- event_crowd 불변식(#276, v2 #282): 그레인(gu_code,day_of_week,hour_of_day) 유일
--   + dow 1~7 + hour 0~23 + congest_score 1~4 + crowd_samples≥1. 위반 행 하나라도 있으면 실패.
with dupes as (
    select gu_code, day_of_week, hour_of_day, count(*) as n
    from {{ ref('gold_culture_event_crowd') }}
    group by gu_code, day_of_week, hour_of_day
    having count(*) > 1
),
bad as (
    select gu_code, day_of_week, hour_of_day
    from {{ ref('gold_culture_event_crowd') }}
    where day_of_week < 1 or day_of_week > 7
       or hour_of_day < 0 or hour_of_day > 23
       or avg_congest_score < 1 or avg_congest_score > 4
       or crowd_samples < 1
)
select gu_code, day_of_week, hour_of_day, 'dupe' as violation from dupes
union all
select gu_code, day_of_week, hour_of_day, 'range' as violation from bad
