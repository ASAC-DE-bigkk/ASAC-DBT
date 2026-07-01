-- silver: KOPIS 예매상황판(boxoffice) top50 인기공연 랭킹 스냅샷.
-- 그레인: (load_date, rank_no). 같은 날 재적재는 최신 ingest_ts만 남긴다.
-- 기간(prfpd 'YYYY.MM.DD~YYYY.MM.DD')을 시작/종료로 분해, 순위·횟수·좌석수는 정수화.

with bronze as (
    select
        json_extract_scalar(record_json, '$.rnum')      as rank_raw,
        json_extract_scalar(record_json, '$.mt20id')    as performance_id,
        json_extract_scalar(record_json, '$.prfnm')     as performance_name,
        json_extract_scalar(record_json, '$.cate')      as genre,
        json_extract_scalar(record_json, '$.prfplcnm')  as venue_name,
        json_extract_scalar(record_json, '$.area')      as area,
        json_extract_scalar(record_json, '$.prfpd')     as period_raw,
        json_extract_scalar(record_json, '$.prfdtcnt')  as perf_count_raw,
        json_extract_scalar(record_json, '$.seatcnt')   as seat_count_raw,
        load_date,
        ingest_ts,
        raw_object_key
    from {{ source('culture_bronze', 'bronze_kopis_boxoffice') }}
),

typed as (
    select
        try(cast(rank_raw as integer))           as rank_no,
        nullif(trim(performance_id), '')         as performance_id,
        nullif(trim(performance_name), '')       as performance_name,
        nullif(trim(genre), '')                  as genre,
        nullif(trim(venue_name), '')             as venue_name,
        nullif(trim(area), '')                   as area,
        -- 기간 'YYYY.MM.DD~YYYY.MM.DD' → 시작/종료 date (파싱 실패는 NULL)
        try(cast(date_parse(trim(split_part(period_raw, '~', 1)), '%Y.%m.%d') as date)) as period_start,
        try(cast(date_parse(trim(split_part(period_raw, '~', 2)), '%Y.%m.%d') as date)) as period_end,
        try(cast(perf_count_raw as integer))     as perf_count,
        try(cast(seat_count_raw as integer))     as seat_count,
        load_date,
        ingest_ts,
        raw_object_key
    from bronze
    where try(cast(rank_raw as integer)) is not null
),

dedup as (
    -- 스냅샷 단위 중복제거: 같은 날·같은 순위면 최신 적재만.
    select *, row_number() over (partition by load_date, rank_no order by ingest_ts desc) as rn
    from typed
)

select
    rank_no,
    performance_id,
    performance_name,
    genre,
    venue_name,
    area,
    period_start,
    period_end,
    perf_count,
    seat_count,
    load_date,
    ingest_ts
from dedup
where rn = 1
