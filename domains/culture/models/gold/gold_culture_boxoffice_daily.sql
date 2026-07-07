-- gold: 예매상황판 랭킹 스냅샷. 공간은 performance(→facility) 경유 best-effort.

with box as (select * from {{ ref('silver_culture_boxoffice') }}),

perf_axis as (
    select performance_id, max(gu_code) as gu_code, max(gu) as gu
    from {{ ref('silver_culture_performance') }}
    where performance_id is not null
    group by performance_id
)

select
    b.load_date as snapshot_date,
    b.rank_no,
    b.performance_id,
    b.performance_name,
    b.genre,
    b.venue_name,
    b.event_start_date,
    b.event_end_date,
    b.perf_count,
    b.seat_count,
    p.gu_code,
    p.gu
from box b
left join perf_axis p on p.performance_id = b.performance_id
