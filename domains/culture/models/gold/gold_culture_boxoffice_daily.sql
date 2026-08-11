-- gold: 예매상황판 랭킹 스냅샷 + 순위 모멘텀. 공간은 performance(→facility) 경유 best-effort.
--   KOPIS 예매율 필드 부재 → 예매 상황은 rank 자체. 모멘텀 = 순위 이동으로 "요즘 뜨는 공연"(#270).
--   "3일 전"은 snapshot_date - 3일 달력 조인(freshness 갭 안전, 3스냅샷 lag 아님).

with box as (
    select
        b.load_date                       as snapshot_date,
        cast(b.load_date as date)         as snapshot_d,
        b.rank_no,
        b.performance_id,
        b.performance_name,
        b.tour_city,
        b.genre,
        b.venue_name,
        b.event_start_date,
        b.event_end_date,
        b.perf_count,
        b.seat_count
    from {{ ref('silver_culture_boxoffice') }} b
),

perf_axis as (
    select
        performance_id,
        max(gu_code)         as gu_code,
        max(gu)              as gu,
        max(admin_dong_code) as admin_dong_code,
        max(admin_dong)      as admin_dong,
        max(longitude)       as longitude,
        max(latitude)        as latitude
    from {{ ref('silver_culture_performance') }}
    where performance_id is not null
    group by performance_id
),

-- 공연×스냅샷일 1행(랭킹이라 통상 유일하나 안전하게 min rank 집계 — 조인 fan-out 방지)
daily_perf as (
    select performance_id, snapshot_d, min(rank_no) as rank_no
    from box
    group by performance_id, snapshot_d
),

-- top50 누적 등장 스냅샷 수(현재 포함)
chart_days as (
    select
        performance_id,
        snapshot_d,
        count(*) over (
            partition by performance_id
            order by snapshot_d
            rows between unbounded preceding and current row
        ) as days_on_chart
    from daily_perf
)

select
    b.snapshot_date,
    b.rank_no,
    b.performance_id,
    b.performance_name,
    b.tour_city,
    b.genre,
    b.venue_name,
    b.event_start_date,
    b.event_end_date,
    b.perf_count,
    b.seat_count,
    p.gu_code,
    p.gu,
    p.admin_dong_code,
    p.admin_dong,
    p.longitude,
    p.latitude,
    -- 모멘텀
    d3.rank_no                                     as rank_prev_3d,
    (d3.rank_no - b.rank_no)                       as rank_delta_3d,
    cast(cd.days_on_chart as integer)              as days_on_chart,
    (d1.performance_id is null)                    as is_new_entry,
    case
        when d1.performance_id is null   then 'new'      -- 어제 부재(첫 진입·재진입)
        when d3.rank_no is null          then 'steady'   -- 어제는 있으나 3일 전 없음(추세 미정)
        when d3.rank_no - b.rank_no > 0  then 'rising'
        when d3.rank_no - b.rank_no < 0  then 'falling'
        else 'steady'
    end                                            as momentum_status
from box b
left join perf_axis p   on p.performance_id = b.performance_id
left join chart_days cd on cd.performance_id = b.performance_id and cd.snapshot_d = b.snapshot_d
left join daily_perf d3 on d3.performance_id = b.performance_id and d3.snapshot_d = b.snapshot_d - interval '3' day
left join daily_perf d1 on d1.performance_id = b.performance_id and d1.snapshot_d = b.snapshot_d - interval '1' day
