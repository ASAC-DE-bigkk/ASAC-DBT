-- gold: culture 활동(공연·행사·축제·전시·세종·kcisa)을 gu_code × 일자로 집계 — #48 코드 축.
-- 기간 → 일자 전개(cross join unnest sequence). 그레인: gu_code × event_date.

with raw_activities as (
    select gu_code, gu, cast(performance_id as varchar) as activity_id, 'performance' as activity_type, event_start_date, event_end_date, quality_status
    from {{ ref('silver_culture_performance') }}
    union all
    select gu_code, gu, event_key, 'event', event_start_date, event_end_date, quality_status
    from {{ ref('silver_culture_event') }}
    union all
    select gu_code, gu, cast(festival_id as varchar), 'festival', event_start_date, event_end_date, quality_status
    from {{ ref('silver_culture_festival') }}
    union all
    select gu_code, gu, cast(exhibition_id as varchar), 'exhibition', event_start_date, event_end_date, quality_status
    from {{ ref('silver_culture_exhibition') }}
    union all
    select gu_code, gu, cast(sejong_id as varchar), 'sejong', event_start_date, event_end_date, quality_status
    from {{ ref('silver_culture_sejong') }}
    union all
    -- kcisa(#85): 3축 dedup 잔존분만 — 기존 type에 합산(id는 sema 숫자키와 충돌 방지 프리픽스)
    select gu_code, gu, 'kcisa:' || event_id,
           case service_name
               when '전시' then 'exhibition'
               when '공연' then 'performance'
               when '행사/축제' then 'festival'
               else 'event'   -- 교육/체험 등
           end,
           event_start_date, event_end_date, quality_status
    from {{ ref('silver_culture_kcisa_event') }}
),

activities as (
    select * from raw_activities
    where gu_code is not null
      and event_start_date is not null
      and event_end_date is not null
      and event_end_date >= event_start_date
      and date_diff('day', event_start_date, event_end_date) <= 400
),

expanded as (
    select a.gu_code, a.gu, a.activity_id, a.activity_type, a.quality_status, d.activity_date
    from activities a
    cross join unnest(sequence(a.event_start_date, a.event_end_date, interval '1' day)) as d(activity_date)
)

select
    gu_code,
    max(gu) as gu,
    activity_date as event_date,
    count(distinct activity_id) as activities_count,
    count(distinct case when activity_type = 'performance' then activity_id end) as performances_count,
    count(distinct case when activity_type = 'event'       then activity_id end) as events_count,
    count(distinct case when activity_type = 'festival'    then activity_id end) as festivals_count,
    count(distinct case when activity_type = 'exhibition'  then activity_id end) as exhibitions_count,
    count(distinct case when activity_type = 'sejong'      then activity_id end) as sejong_count,
    count(distinct case when quality_status = 'dong_precise' then activity_id end) as dong_precise_count
from expanded
group by gu_code, activity_date
