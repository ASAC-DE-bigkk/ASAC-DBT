-- silver: KOPIS 공연목록 bronze(record_json)를 파싱·타입화·중복제거.
-- 계약: event_time(공연 기간) ≠ ingest_time(ingest_ts).
-- location_key = 공연장→자치구 매핑(facility의 gugunnm). 미매칭은 공연장명으로 폴백.

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
),

latest as (
    select * from dedup where rn = 1
),

-- 공연장명 → 자치구 매핑 (이름당 1행 보장, fan-out 방지)
facility_gu as (
    select
        facility_name,
        max(location_key) as gu,
        max(facility_id)  as facility_id
    from {{ ref('silver_culture_facility') }}
    where facility_name is not null
    group by facility_name
)

select
    l.performance_id,
    l.performance_name,
    l.genre,
    l.venue_name,
    f.facility_id,
    -- 공용 location_key: 자치구(매핑 성공) 또는 공연장명(폴백)
    coalesce(f.gu, l.venue_name)                                  as location_key,
    case when f.gu is not null then 'gu' else 'venue_fallback' end as location_key_level,
    l.performance_state,
    l.area,
    l.period_start,
    l.period_end,
    l.load_date,
    l.ingest_ts
from latest l
left join facility_gu f
    on l.venue_name = f.facility_name
