-- silver: KOPIS 공연목록 bronze(record_json)를 파싱·타입화·중복제거.
-- 계약: event_time(공연 기간) ≠ ingest_time(ingest_ts), 공용 location_key(1단계 임시=공연장명).

with bronze as (
    select
        json_extract_scalar(record_json, '$.mt20id')    as performance_id,
        json_extract_scalar(record_json, '$.prfnm')     as performance_name,
        json_extract_scalar(record_json, '$.genrenm')   as genre,
        json_extract_scalar(record_json, '$.fcltynm')   as venue_name,
        json_extract_scalar(record_json, '$.prfstate')  as performance_state,
        json_extract_scalar(record_json, '$.area')      as area,
        json_extract_scalar(record_json, '$.prfpdfrom') as period_from_raw,
        json_extract_scalar(record_json, '$.prfpdto')   as period_to_raw,
        load_date,
        ingest_ts,
        raw_object_key
    from {{ source('culture_bronze', 'bronze_kopis_performance') }}
),

typed as (
    select
        performance_id,
        nullif(trim(performance_name), '')  as performance_name,
        nullif(trim(genre), '')             as genre,
        nullif(trim(venue_name), '')        as venue_name,
        nullif(trim(performance_state), '') as performance_state,
        nullif(trim(area), '')              as area,
        -- KOPIS 날짜는 'YYYY.MM.DD' → date. 파싱 실패는 NULL.
        try(cast(date_parse(period_from_raw, '%Y.%m.%d') as date)) as period_start,
        try(cast(date_parse(period_to_raw, '%Y.%m.%d') as date))   as period_end,
        -- 공용 location_key: 1단계 임시 = 공연장명(자치구 매핑은 facility 좌표 조인 후속)
        nullif(trim(venue_name), '')        as location_key,
        load_date,
        ingest_ts,
        raw_object_key
    from bronze
    where performance_id is not null
),

dedup as (
    select
        *,
        row_number() over (partition by performance_id order by ingest_ts desc) as rn
    from typed
)

select
    performance_id,
    performance_name,
    genre,
    venue_name,
    location_key,
    performance_state,
    area,
    period_start,
    period_end,
    load_date,
    ingest_ts
from dedup
where rn = 1
