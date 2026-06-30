-- silver: KOPIS 축제(prffest). 공연과 동일 구조 — 공연장명→facility로 자치구 매핑.
-- location_key = 자치구(매핑 성공) 또는 NULL(미매칭 → gold 제외).

with bronze as (
    select
        json_extract_scalar(record_json, '$.mt20id')    as festival_id,
        json_extract_scalar(record_json, '$.prfnm')     as festival_name,
        json_extract_scalar(record_json, '$.genrenm')   as genre,
        json_extract_scalar(record_json, '$.fcltynm')   as venue_name,
        json_extract_scalar(record_json, '$.prfpdfrom') as period_from_raw,
        json_extract_scalar(record_json, '$.prfpdto')   as period_to_raw,
        ingest_ts
    from {{ source('culture_bronze', 'bronze_kopis_festival') }}
),

typed as (
    select
        festival_id,
        nullif(trim(festival_name), '') as festival_name,
        nullif(trim(genre), '')         as genre,
        nullif(trim(venue_name), '')    as venue_name,
        try(cast(date_parse(period_from_raw, '%Y.%m.%d') as date)) as period_start,
        try(cast(date_parse(period_to_raw, '%Y.%m.%d') as date))   as period_end,
        ingest_ts
    from bronze
    where festival_id is not null
),

dedup as (
    select *, row_number() over (partition by festival_id order by ingest_ts desc) as rn
    from typed
),

latest as (select * from dedup where rn = 1),

facility_gu as (
    select facility_name, max(location_key) as gu
    from {{ ref('silver_culture_facility') }}
    where facility_name is not null
    group by facility_name
)

select
    l.festival_id,
    l.festival_name,
    l.genre,
    l.venue_name,
    f.gu as location_key,   -- 자치구 (미매칭은 NULL)
    l.period_start,
    l.period_end
from latest l
left join facility_gu f on l.venue_name = f.facility_name
