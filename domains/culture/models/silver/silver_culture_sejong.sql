-- silver: 세종문화회관 공연/전시 기간 fact. 단일 시설 → 위치는 sejong_location seed 상수(cross join 1행).
--
-- 최신 load_date 파티션만 읽는다(#329). bronze 는 매일 전체 스냅샷을 append 하므로 전량 스캔하면
-- 메모리가 누적일수에 비례해 늘고 상한이 없다 — 22일치 1,962MB 를 읽어 최신 1일치 산출을 만들다
-- Trino per-node 2GB 한도를 쳤다. 원천이 매일 전량을 다시 주므로 최신 파티션만으로 산출은 동일하다.
-- 하루 안에서는 여전히 중복이 생기므로(수동 재적재 시 같은 load_date 에 여러 스냅샷) 아래 dedup 은 유지한다.

with latest_load as (
    select max(load_date) as load_date
    from {{ source('culture_bronze', 'bronze_seoul_sejong') }}
),

bronze as (
    select
        json_extract_scalar(record_json, '$.PERFORM_IDX') as sejong_id,
        json_extract_scalar(record_json, '$.TITLE')       as title_raw,
        json_extract_scalar(record_json, '$.GENRE_NAME')  as genre,
        json_extract_scalar(record_json, '$.PLACE_LIST')  as venue_raw,
        json_extract_scalar(record_json, '$.START_DATE')  as start_raw,
        json_extract_scalar(record_json, '$.END_DATE')    as end_raw,
        ingest_ts,
        {{ culture_lineage('seoul') }}
    from {{ source('culture_bronze', 'bronze_seoul_sejong') }}
    where load_date = (select load_date from latest_load)
),

latest as (
    select * from (
        select
            sejong_id,
            nullif(trim(title_raw), '') as title,
            nullif(trim(genre), '')     as genre,
            nullif(trim(venue_raw), '') as venue_name,
            try(cast(date_parse(start_raw, '%Y%m%d') as date)) as event_start_date,
            try(cast(date_parse(end_raw, '%Y%m%d') as date))   as event_end_date,
            source_system, dag_run_id, raw_object_key, collected_at, ingested_at, load_date,
            row_number() over (partition by sejong_id order by {{ culture_dedup_order() }}) as rn
        from bronze
        where sejong_id is not null
    ) where rn = 1
),

placed as (
    select l.*, s.gu, s.latitude, s.longitude
    from latest l
    cross join {{ ref('sejong_location') }} s
),

dong_map as {{ culture_dong_map('placed') }},

{{ culture_admin_canon() }},

stamped as (
select
    p.sejong_id, p.title, p.genre, p.venue_name,
    p.event_start_date, p.event_end_date,
    cast(p.event_start_date as timestamp(6)) as event_at,
    p.longitude, p.latitude, p.gu,
    {{ culture_admin_stamp_cols() }},
    p.source_system, p.dag_run_id, p.raw_object_key, p.collected_at, p.ingested_at, p.load_date
from placed p
{{ culture_admin_stamp_joins('p') }}
)

select *, {{ culture_quality_status() }} as quality_status
from stamped
