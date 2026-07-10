-- silver: KOPIS 공연 기간 fact. 시설 축은 detail(mt10id) 정밀 조인 + 이름 매칭 폴백 —
-- 기존 이름 단독 매칭의 동명 시설 임의 선택을 해소(설계 §2). 공간축은 facility dim 경유.

with list_bronze as (
    select
        json_extract_scalar(record_json, '$.mt20id')    as performance_id,
        json_extract_scalar(record_json, '$.prfnm')     as performance_name,
        json_extract_scalar(record_json, '$.genrenm')   as genre,
        json_extract_scalar(record_json, '$.fcltynm')   as venue_name,
        json_extract_scalar(record_json, '$.prfstate')  as state,
        json_extract_scalar(record_json, '$.prfpdfrom') as start_raw,
        json_extract_scalar(record_json, '$.prfpdto')   as end_raw,
        ingest_ts,
        {{ culture_lineage('kopis') }}
    from {{ source('culture_bronze', 'bronze_kopis_performance') }}
),

list_latest as (
    select * from (
        select
            performance_id,
            nullif(trim(performance_name), '') as performance_name,
            nullif(trim(genre), '')            as genre,
            nullif(trim(venue_name), '')       as venue_name,
            nullif(trim(state), '')            as state,
            try(cast(date_parse(trim(start_raw), '%Y.%m.%d') as date)) as event_start_date,
            try(cast(date_parse(trim(end_raw), '%Y.%m.%d') as date))   as event_end_date,
            source_system, dag_run_id, raw_object_key, collected_at, ingested_at, load_date,
            row_number() over (partition by performance_id order by {{ culture_dedup_order() }}) as rn
        from list_bronze
        where performance_id is not null
    ) where rn = 1
),

detail_latest as (
    select * from (
        select
            json_extract_scalar(record_json, '$.mt20id') as performance_id,
            json_extract_scalar(record_json, '$.mt10id') as facility_id,
            row_number() over (
                partition by json_extract_scalar(record_json, '$.mt20id')
                order by {{ culture_dedup_order() }}
            ) as rn
        from {{ source('culture_bronze', 'bronze_kopis_performance_detail') }}
        where json_extract_scalar(record_json, '$.mt10id') is not null
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
),

resolved as (
    select
        l.*,
        coalesce(d.facility_id, n.facility_id) as facility_id,
        case when d.facility_id is not null then 'detail_id'
             when n.facility_id is not null then 'name' end as facility_match
    from list_latest l
    left join detail_latest d on d.performance_id = l.performance_id
    left join fac_by_name n on n.facility_name = l.venue_name
),

stamped as (
select
    r.performance_id, r.performance_name, r.genre, r.state, r.venue_name,
    r.facility_id, r.facility_match,
    r.event_start_date, r.event_end_date,
    cast(r.event_start_date as timestamp(6)) as event_at,
    f.longitude, f.latitude, f.gu, f.gu_code, f.admin_dong, f.admin_dong_code,
    r.source_system, r.dag_run_id, r.raw_object_key, r.collected_at, r.ingested_at, r.load_date
from resolved r
left join fac f on f.facility_id = r.facility_id
)

select *, {{ culture_quality_status() }} as quality_status
from stamped
