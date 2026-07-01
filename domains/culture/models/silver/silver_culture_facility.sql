-- silver: KOPIS 공연시설(prfplc) 차원. 공연장 → 자치구(gugunnm) 매핑의 원천.
-- mt10id 기준 중복제거. location_key(자치구)를 노출해 공연 silver가 조인하게 한다.

with bronze as (
    select
        json_extract_scalar(record_json, '$.mt10id')  as facility_id,
        json_extract_scalar(record_json, '$.fcltynm') as facility_name,
        json_extract_scalar(record_json, '$.sidonm')  as sido,
        json_extract_scalar(record_json, '$.gugunnm') as gu,
        ingest_ts
    from {{ source('culture_bronze', 'bronze_kopis_facility') }}
),

dedup as (
    select
        facility_id,
        nullif(trim(facility_name), '') as facility_name,
        nullif(trim(sido), '')          as sido,
        nullif(trim(gu), '')            as location_key,   -- 자치구
        row_number() over (partition by facility_id order by ingest_ts desc) as rn
    from bronze
    where facility_id is not null
)

select
    facility_id,
    facility_name,
    sido,
    location_key
from dedup
where rn = 1
