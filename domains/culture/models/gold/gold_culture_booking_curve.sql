-- gold: 공연별 예매상황판 순위 궤적 요약(그레인 performance_id, 1공연 1행).
--   KOPIS 예매상황판은 순위(rank)만 제공 — 예매율·판매좌석·매진 데이터 없음(#274).
--   그래서 '예매율 곡선'이 아니라 top50 등장 이력의 순위 궤적을 롤업한다.
--   boxoffice_daily(스냅샷별)와 그레인이 다름 — 여기는 공연 1행 요약.

with box as (
    select
        performance_id,
        performance_name,
        genre,
        venue_name,
        event_start_date,
        event_end_date,
        cast(load_date as date) as snapshot_d,
        rank_no
    from {{ ref('silver_culture_boxoffice') }}
    where performance_id is not null
)

select
    performance_id,
    max(performance_name)                                          as performance_name,
    max(genre)                                                     as genre,
    max(venue_name)                                                as venue_name,
    max(event_start_date)                                          as event_start_date,
    max(event_end_date)                                            as event_end_date,
    min(snapshot_d)                                                as first_seen_date,
    max(snapshot_d)                                                as last_seen_date,
    cast(count(distinct snapshot_d) as integer)                    as days_on_chart,
    cast(min(rank_no) as integer)                                  as best_rank,
    min_by(snapshot_d, rank_no)                                    as best_rank_date,
    cast(date_diff('day', min(snapshot_d), min_by(snapshot_d, rank_no)) as integer) as days_to_peak,
    cast(min_by(rank_no, snapshot_d) as integer)                   as first_rank,
    cast(max_by(rank_no, snapshot_d) as integer)                   as last_rank
from box
group by performance_id
