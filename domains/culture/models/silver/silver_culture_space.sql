-- silver: 서울 문화공간 dim. ⚠️ 좌표 축 스왑: X_COORD=위도, Y_COORD=경도.
-- space_key: Task 2 실측: NUM 안정 → NUM 채택 (unstable_nums=0, 6일간 1:1 안정).

with bronze as (
    select
        json_extract_scalar(record_json, '$.NUM')      as num_raw,
        json_extract_scalar(record_json, '$.FAC_NAME') as fac_name,
        json_extract_scalar(record_json, '$.GNGU')     as gu_raw,
        json_extract_scalar(record_json, '$.ADDR')     as addr,
        json_extract_scalar(record_json, '$.SUBJCODE') as subject_code,
        json_extract_scalar(record_json, '$.X_COORD')  as lat_raw,   -- 위도
        json_extract_scalar(record_json, '$.Y_COORD')  as lon_raw,   -- 경도
        ingest_ts,
        {{ culture_lineage('seoul') }}
    from {{ source('culture_bronze', 'bronze_seoul_cultural_space') }}
),

typed as (
    select
        num_raw                        as space_key,
        nullif(trim(fac_name), '')     as facility_name,
        nullif(trim(gu_raw), '')       as gu,
        nullif(trim(addr), '')         as address,
        nullif(trim(subject_code), '') as subject_code,
        {{ asac_axes.seoul_lonlat('lon_raw', 'lat_raw') }},
        ingest_ts, source_system, dag_run_id, raw_object_key, collected_at, ingested_at, load_date
    from bronze
    where nullif(trim(fac_name), '') is not null
      and num_raw is not null
),

latest as (
    select * from (
        select *, row_number() over (partition by space_key order by {{ culture_dedup_order() }}) as rn
        from typed
    ) where rn = 1
),

dong_map as {{ culture_dong_map('latest') }},

{{ culture_admin_canon() }},

stamped as (
select
    l.space_key, l.facility_name, l.gu, l.address, l.subject_code,
    l.longitude, l.latitude,
    {{ culture_admin_stamp_cols() }},
    l.source_system, l.dag_run_id, l.raw_object_key, l.collected_at, l.ingested_at, l.load_date
from latest l
{{ culture_admin_stamp_joins('l') }}
)

select *, {{ culture_quality_status() }} as quality_status
from stamped
