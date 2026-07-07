-- silver: 세종문화회관 공연/전시 기간 fact. 단일 시설 → 위치는 sejong_location seed 상수(cross join 1행).

with bronze as (
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

gu_codes as (select distinct gu, gu_code from {{ ref('seoul_admin_dong_crosswalk') }})

select
    p.sejong_id, p.title, p.genre, p.venue_name,
    p.event_start_date, p.event_end_date,
    cast(p.event_start_date as timestamp(6)) as event_at,
    p.longitude, p.latitude, p.gu,
    coalesce(g.gu_code, d.coord_gu_code) as gu_code,
    d.admin_dong, d.admin_dong_code,
    p.source_system, p.dag_run_id, p.raw_object_key, p.collected_at, p.ingested_at, p.load_date
from placed p
left join dong_map d on p.longitude = d.longitude and p.latitude = d.latitude
left join gu_codes g on g.gu = p.gu
