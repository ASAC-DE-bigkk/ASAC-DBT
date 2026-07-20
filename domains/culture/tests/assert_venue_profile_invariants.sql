-- venue_profile 불변식(#278): 그레인(facility_id) 유일 + perf_count>=0
--   + perf_count=0 → top_genre null(단방향 — genre null 공연 존재 가능해 역방향 미보장)
--   + first_perf_date <= last_perf_date.
with dupes as (
    select facility_id, count(*) as n
    from {{ ref('gold_culture_venue_profile') }}
    group by facility_id
    having count(*) > 1
),
bad as (
    select facility_id
    from {{ ref('gold_culture_venue_profile') }}
    where perf_count < 0
       or (perf_count = 0 and top_genre is not null)
       or (first_perf_date is not null and last_perf_date is not null
           and first_perf_date > last_perf_date)
)
select facility_id, 'dupe' as violation from dupes
union all
select facility_id, 'invariant' as violation from bad
