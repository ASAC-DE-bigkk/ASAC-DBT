-- silver: KOPIS 예매상황판 일 스냅샷 fact (top50 랭킹). 그레인 = (load_date, rank_no).
-- 공간축 면제(area=시도뿐 — 설계 §2). 랭킹 대상 기간은 event_start/end 로 보존.

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
        ingest_ts,
        {{ culture_lineage('kopis') }}
    from {{ source('culture_bronze', 'bronze_kopis_boxoffice') }}
),

typed as (
    select
        try(cast(rank_raw as integer))                   as rank_no,
        performance_id,
        nullif(trim(performance_name), '')               as performance_name,
        -- KOPIS 투어 공연은 제목 끝에 "[서울]" 같은 도시 접미사가 붙는다(원천 관행).
        -- 장소 필드가 아니므로 별도 컬럼으로 분리해 하위 소비자의 오독을 막는다(#509).
        nullif(trim(regexp_extract(trim(performance_name), '\[([^\[\]]+)\]$', 1)), '') as tour_city,
        nullif(trim(genre), '')                          as genre,
        nullif(trim(venue_name), '')                     as venue_name,
        nullif(trim(area), '')                           as area,
        try(cast(date_parse(trim(split_part(period_raw, '~', 1)), '%Y.%m.%d') as date)) as event_start_date,
        try(cast(date_parse(trim(split_part(period_raw, '~', 2)), '%Y.%m.%d') as date)) as event_end_date,
        try(cast(replace(perf_count_raw, ',', '') as integer)) as perf_count,
        try(cast(replace(seat_count_raw, ',', '') as integer)) as seat_count,
        ingest_ts, source_system, dag_run_id, raw_object_key, collected_at, ingested_at, load_date
    from bronze
    where try(cast(rank_raw as integer)) is not null
)

select
    rank_no, performance_id, performance_name, tour_city, genre, venue_name, area,
    event_start_date, event_end_date,
    cast(try(cast(load_date as date)) as timestamp(6)) as event_at,
    perf_count, seat_count,
    source_system, dag_run_id, raw_object_key, collected_at, ingested_at, load_date
from (
    select *, row_number() over (
        partition by load_date, rank_no
        order by {{ culture_dedup_order() }}
    ) as rn
    from typed
) where rn = 1
