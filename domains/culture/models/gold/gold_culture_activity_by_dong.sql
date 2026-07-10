-- gold: 행정동(admin_dong) × 일자 문화활동 집계 — bronze canonical 소비 첫 gold(#48).
-- dim_admin_dong(426동)을 활동 일자 spine과 cross join한 scaffold에 활동을 left join →
-- 활동 0건 행정동도 0으로 행 존재(지도 빈칸 방지, dim 문서 권장 패턴).
-- sports(야구)는 문화활동 축 아님 → 제외(gold_culture_location_daily 관례 유지).

with dim as (
    select admin_dong_code, admin_dong, gu_code, gu, stat_region_cd
    from {{ ref('asac_axes', 'dim_admin_dong') }}
),

raw_activities as (
    select admin_dong_code, cast(performance_id as varchar) as activity_id, 'performance' as activity_type, event_start_date, event_end_date
    from {{ ref('silver_culture_performance') }}
    union all
    select admin_dong_code, event_key, 'event', event_start_date, event_end_date
    from {{ ref('silver_culture_event') }}
    union all
    select admin_dong_code, cast(festival_id as varchar), 'festival', event_start_date, event_end_date
    from {{ ref('silver_culture_festival') }}
    union all
    select admin_dong_code, cast(exhibition_id as varchar), 'exhibition', event_start_date, event_end_date
    from {{ ref('silver_culture_exhibition') }}
    union all
    select admin_dong_code, cast(sejong_id as varchar), 'sejong', event_start_date, event_end_date
    from {{ ref('silver_culture_sejong') }}
    union all
    select admin_dong_code, 'kcisa:' || event_id, 'kcisa', event_start_date, event_end_date
    from {{ ref('silver_culture_kcisa_event') }}
),

activities as (
    select * from raw_activities
    where admin_dong_code is not null
      and event_start_date is not null
      and event_end_date is not null
      and event_end_date >= event_start_date
      and date_diff('day', event_start_date, event_end_date) <= 400
),

expanded as (
    select a.admin_dong_code, a.activity_id, a.activity_type, d.activity_date
    from activities a
    cross join unnest(sequence(a.event_start_date, a.event_end_date, interval '1' day)) as d(activity_date)
),

-- date_spine 은 최근 창 [today-90, today+365] 으로 제한 — 27년치 scaffold(3.9M행·96% 0)
-- 방지. "0건 동 표현"은 현재~근미래 지도에만 유의미(과거/먼미래 0-fill 불요).
date_spine as (
    select distinct activity_date as event_date
    from expanded
    where activity_date between date_add('day', -90, current_date)
                           and date_add('day', 365, current_date)
),

scaffold as (
    select dim.admin_dong_code, dim.admin_dong, dim.gu_code, dim.gu, dim.stat_region_cd, ds.event_date
    from dim
    cross join date_spine ds
),

agg as (
    select
        admin_dong_code,
        activity_date as event_date,
        count(distinct activity_id) as activities_count,
        count(distinct case when activity_type = 'performance' then activity_id end) as performances_count,
        count(distinct case when activity_type = 'event'       then activity_id end) as events_count,
        count(distinct case when activity_type = 'festival'    then activity_id end) as festivals_count,
        count(distinct case when activity_type = 'exhibition'  then activity_id end) as exhibitions_count,
        count(distinct case when activity_type = 'sejong'      then activity_id end) as sejong_count,
        count(distinct case when activity_type = 'kcisa'       then activity_id end) as kcisa_count
    from expanded
    group by admin_dong_code, activity_date
)

select
    s.admin_dong_code, s.admin_dong, s.gu_code, s.gu, s.stat_region_cd,
    s.event_date,
    coalesce(a.activities_count, 0)   as activities_count,
    coalesce(a.performances_count, 0) as performances_count,
    coalesce(a.events_count, 0)       as events_count,
    coalesce(a.festivals_count, 0)    as festivals_count,
    coalesce(a.exhibitions_count, 0)  as exhibitions_count,
    coalesce(a.sejong_count, 0)       as sejong_count,
    coalesce(a.kcisa_count, 0)        as kcisa_count
from scaffold s
left join agg a on a.admin_dong_code = s.admin_dong_code and a.event_date = s.event_date
