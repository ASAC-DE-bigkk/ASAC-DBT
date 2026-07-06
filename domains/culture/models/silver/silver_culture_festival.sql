-- silver: KOPIS 축제 기간 fact. detail 미수집 → 시설은 이름 매칭만(미매칭 NULL 허용, 매칭률 테스트 감시).

with bronze as (
    select
        json_extract_scalar(record_json, '$.mt20id')    as festival_id,
        json_extract_scalar(record_json, '$.prfnm')     as festival_name,
        json_extract_scalar(record_json, '$.genrenm')   as genre,
        json_extract_scalar(record_json, '$.fcltynm')   as venue_name,
        json_extract_scalar(record_json, '$.prfpdfrom') as start_raw,
        json_extract_scalar(record_json, '$.prfpdto')   as end_raw,
        ingest_ts,
        {{ culture_lineage('kopis') }}
    from {{ source('culture_bronze', 'bronze_kopis_festival') }}
),

latest as (
    select * from (
        select
            festival_id,
            nullif(trim(festival_name), '') as festival_name,
            nullif(trim(genre), '')         as genre,
            nullif(trim(venue_name), '')    as venue_name,
            try(cast(date_parse(trim(start_raw), '%Y.%m.%d') as date)) as event_start_date,
            try(cast(date_parse(trim(end_raw), '%Y.%m.%d') as date))   as event_end_date,
            source_system, dag_run_id, raw_object_key, collected_at, ingested_at, load_date,
            row_number() over (partition by festival_id order by {{ culture_dedup_order() }}) as rn
        from bronze
        where festival_id is not null
    ) where rn = 1
),

fac as (
    select facility_id, facility_name, longitude, latitude, gu, gu_code, admin_dong, admin_dong_code
    from {{ ref('silver_culture_facility') }}
),

fac_by_name as (
    select facility_name, min(facility_id) as facility_id
    from fac
    where facility_name is not null
    group by facility_name
)

select
    l.festival_id, l.festival_name, l.genre, l.venue_name,
    n.facility_id,
    case when n.facility_id is not null then 'name' end as facility_match,
    l.event_start_date, l.event_end_date,
    cast(l.event_start_date as timestamp(6)) as event_at,
    f.longitude, f.latitude, f.gu, f.gu_code, f.admin_dong, f.admin_dong_code,
    l.source_system, l.dag_run_id, l.raw_object_key, l.collected_at, l.ingested_at, l.load_date
from latest l
left join fac_by_name n on n.facility_name = l.venue_name
left join fac f on f.facility_id = n.facility_id
