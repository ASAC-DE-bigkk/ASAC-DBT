-- silver: 서울 문화행사정보(culturalEventInfo) bronze를 파싱·타입화·중복제거.
-- location_key = GUNAME(자치구) 직결. event_time = 행사 기간(STRTDATE~END_DATE).
-- 자연키가 없어 (제목·시작일·장소) 해시를 surrogate event_key로 사용.
-- 좌표: LOT(경도)/LAT(위도) → longitude/latitude 정규화.

with bronze as (
    select
        json_extract_scalar(record_json, '$.TITLE')    as event_title,
        json_extract_scalar(record_json, '$.GUNAME')   as gu,
        json_extract_scalar(record_json, '$.PLACE')    as place,
        json_extract_scalar(record_json, '$.CODENAME') as category,
        json_extract_scalar(record_json, '$.IS_FREE')  as is_free,
        json_extract_scalar(record_json, '$.STRTDATE') as strt_raw,
        json_extract_scalar(record_json, '$.END_DATE') as end_raw,
        json_extract_scalar(record_json, '$.LOT')      as lot_raw,
        json_extract_scalar(record_json, '$.LAT')      as lat_raw,
        load_date,
        ingest_ts,
        raw_object_key
    from {{ source('culture_bronze', 'bronze_seoul_cultural_event') }}
),

typed as (
    select
        nullif(trim(event_title), '') as event_title,
        nullif(trim(gu), '')          as location_key,   -- 자치구(GUNAME)
        nullif(trim(place), '')       as place,
        nullif(trim(category), '')    as category,
        nullif(trim(is_free), '')     as is_free,
        -- 'YYYY-MM-DD HH:MM:SS.0' → 앞 10자리 = date
        try(cast(substr(strt_raw, 1, 10) as date)) as period_start,
        try(cast(substr(end_raw, 1, 10) as date))  as period_end,
        -- 좌표: LOT=경도, LAT=위도
        {{ seoul_lonlat('lot_raw', 'lat_raw') }},
        load_date,
        ingest_ts,
        raw_object_key
    from bronze
    where nullif(trim(event_title), '') is not null
),

keyed as (
    select
        to_hex(md5(to_utf8(concat_ws(
            '|',
            coalesce(event_title, ''),
            coalesce(cast(period_start as varchar), ''),
            coalesce(place, '')
        )))) as event_key,
        typed.*
    from typed
),

dedup as (
    select
        *,
        row_number() over (partition by event_key order by ingest_ts desc) as rn
    from keyed
)

select
    event_key,
    event_title,
    location_key,
    place,
    category,
    is_free,
    period_start,
    period_end,
    longitude,
    latitude,
    load_date,
    ingest_ts
from dedup
where rn = 1
