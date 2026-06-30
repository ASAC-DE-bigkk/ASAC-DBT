-- silver: 세종문화회관 공연/전시(SJWPerform). 세종문화회관은 종로구에 위치 → location_key 상수.
-- 날짜는 'YYYYMMDD'.

with bronze as (
    select
        json_extract_scalar(record_json, '$.PERFORM_IDX') as sejong_id,
        json_extract_scalar(record_json, '$.TITLE')       as title,
        json_extract_scalar(record_json, '$.GENRE_NAME')  as genre,
        json_extract_scalar(record_json, '$.PLACE_LIST')  as venue_name,
        json_extract_scalar(record_json, '$.START_DATE')  as strt_raw,
        json_extract_scalar(record_json, '$.END_DATE')    as end_raw,
        ingest_ts
    from {{ source('culture_bronze', 'bronze_seoul_sejong') }}
),

typed as (
    select
        sejong_id,
        nullif(trim(title), '')      as title,
        nullif(trim(genre), '')      as genre,
        nullif(trim(venue_name), '') as venue_name,
        try(cast(date_parse(strt_raw, '%Y%m%d') as date)) as period_start,
        try(cast(date_parse(end_raw, '%Y%m%d') as date))  as period_end,
        '종로구' as location_key,    -- 세종문화회관 = 종로구
        ingest_ts
    from bronze
    where sejong_id is not null
),

dedup as (
    select *, row_number() over (partition by sejong_id order by ingest_ts desc) as rn
    from typed
)

select
    sejong_id,
    title,
    genre,
    venue_name,
    location_key,
    period_start,
    period_end
from dedup
where rn = 1
