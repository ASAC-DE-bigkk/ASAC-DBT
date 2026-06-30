-- gold: KOPIS 예매상황판 인기공연 랭킹 (스냅샷 append).
-- 그레인: snapshot_date × rank_no. 구간형/예약 gold와 또 다른 "랭킹 팩트".
-- location_key(자치구)는 공연ID(mt20id)→공연 매핑 best-effort. 대부분 NULL
-- (랭킹 상위 공연이 공연목록 적재창과 달라 매칭률 낮음 — 자치구 마스터 보강은 후속).

with box as (
    select * from {{ ref('silver_culture_boxoffice') }}
),

perf_gu as (
    -- 공연ID당 자치구 (매핑 'gu' 레벨만; 폴백 공연장명은 location_key로 안 씀)
    select
        performance_id,
        max(case when location_key_level = 'gu' then location_key end) as location_key
    from {{ ref('silver_culture_performance') }}
    where performance_id is not null
    group by performance_id
)

select
    b.load_date        as snapshot_date,
    b.rank_no,
    b.performance_id,
    b.performance_name,
    b.genre,
    b.venue_name,
    b.period_start,
    b.period_end,
    b.perf_count,
    b.seat_count,
    p.location_key     as location_key
from box b
left join perf_gu p on b.performance_id = p.performance_id
