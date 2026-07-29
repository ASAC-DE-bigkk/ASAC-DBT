-- gold(Q&A metric): 시설 1행 프로필 — "그 공연장 어떤 곳이야"(#278). facility dim(주소·좌표는
-- dong_precise 한정 100% — 신규 시설은 상세 수집 전까지 gu_only·null 로 하루 존재, #364;
-- seat_scale 63.7% 충전) + KOPIS 공연 집계(facility_id 링크 99.9%, 공연 보유 시설 421).
-- ⚠ 공연 통계는 KOPIS 공연 기준(전시·축제·행사 미포함). perf_count=0 시설도 위치·규모 프로필로 유효.
-- meta.external=false — 외부 카탈로그 비공개(Q&A 전용), 대시보드 external 플래그의 소스 오브 트루스(#269).

with fac as (
    select facility_id, facility_name, address, latitude, longitude, seat_scale,
           gu, gu_code, admin_dong, admin_dong_code, quality_status
    from {{ ref('silver_culture_facility') }}
),

perf as (
    select
        facility_id,
        count(*)              as perf_count,
        count(distinct genre) as distinct_genres,
        min(event_start_date) as first_perf_date,
        max(event_end_date)   as last_perf_date
    from {{ ref('silver_culture_performance') }}
    where facility_id is not null
    group by facility_id
),

genre_counts as (
    select facility_id, genre, count(*) as n
    from {{ ref('silver_culture_performance') }}
    where facility_id is not null and genre is not null
    group by facility_id, genre
),

top_genre as (
    select facility_id, max_by(genre, n) as top_genre, max(n) as top_genre_count
    from genre_counts
    group by facility_id
)

select
    f.facility_id,
    f.facility_name,
    f.address,
    f.latitude,
    f.longitude,
    f.seat_scale,
    f.gu,
    f.gu_code,
    f.admin_dong,
    f.admin_dong_code,
    cast(coalesce(p.perf_count, 0) as integer)      as perf_count,
    cast(coalesce(p.distinct_genres, 0) as integer) as distinct_genres,
    t.top_genre,
    cast(t.top_genre_count as integer)              as top_genre_count,
    p.first_perf_date,
    p.last_perf_date,
    f.quality_status
from fac f
left join perf p on p.facility_id = f.facility_id
left join top_genre t on t.facility_id = f.facility_id
