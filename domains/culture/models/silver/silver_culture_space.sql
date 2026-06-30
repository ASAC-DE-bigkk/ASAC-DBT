-- silver: 서울 문화공간정보(culturalSpaceInfo) — 문화공간 차원(시설 마스터).
-- location_key = GNGU(자치구). ⚠️ 좌표 축 주의: X_COORD=위도, Y_COORD=경도 → 정규화.
-- SCD2 차원이지만 현재는 최신 스냅샷(NUM 기준 dedup).

with bronze as (
    select
        json_extract_scalar(record_json, '$.NUM')      as space_id,
        json_extract_scalar(record_json, '$.FAC_NAME') as facility_name,
        json_extract_scalar(record_json, '$.GNGU')     as gu,
        json_extract_scalar(record_json, '$.ADDR')     as address,
        json_extract_scalar(record_json, '$.SUBJCODE') as subject_code,
        json_extract_scalar(record_json, '$.X_COORD')  as x_coord,   -- 위도
        json_extract_scalar(record_json, '$.Y_COORD')  as y_coord,   -- 경도
        ingest_ts
    from {{ source('culture_bronze', 'bronze_seoul_cultural_space') }}
),

typed as (
    select
        nullif(trim(space_id), '')      as space_id,
        nullif(trim(facility_name), '') as facility_name,
        nullif(trim(gu), '')            as location_key,   -- 자치구(GNGU)
        nullif(trim(address), '')       as address,
        nullif(trim(subject_code), '')  as subject_code,
        -- 축 매핑: 경도=Y_COORD, 위도=X_COORD
        {{ seoul_lonlat('y_coord', 'x_coord') }},
        ingest_ts
    from bronze
    where nullif(trim(space_id), '') is not null
),

dedup as (
    select *, row_number() over (partition by space_id order by ingest_ts desc) as rn
    from typed
)

select
    space_id,
    facility_name,
    location_key,
    address,
    subject_code,
    longitude,
    latitude,
    ingest_ts
from dedup
where rn = 1
