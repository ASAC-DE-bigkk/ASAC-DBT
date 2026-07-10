-- silver: KOPIS 공연시설 dim — 목록(prfplc) + 상세(la/lo·adres) 병합. KOPIS 계열 좌표 허브.
-- 상세는 max_detail 캡으로 부분 수집(설계 §5) → left join fail-open, 좌표 없는 시설도 구 레벨 유지.
-- SCD2 는 의도적 보류(설계 §3-C) — bronze 가 전 이력 박제, v1 은 최신본 dim.

with list_bronze as (
    select
        json_extract_scalar(record_json, '$.mt10id')  as facility_id,
        json_extract_scalar(record_json, '$.fcltynm') as facility_name,
        json_extract_scalar(record_json, '$.sidonm')  as sido,
        json_extract_scalar(record_json, '$.gugunnm') as gu_raw,
        ingest_ts,
        {{ culture_lineage('kopis') }}
    from {{ source('culture_bronze', 'bronze_kopis_facility') }}
),

list_latest as (
    select * from (
        select
            facility_id,
            nullif(trim(facility_name), '') as facility_name,
            nullif(trim(sido), '')          as sido,
            nullif(trim(gu_raw), '')        as gu,
            source_system, dag_run_id, raw_object_key, collected_at, ingested_at, load_date,
            row_number() over (partition by facility_id order by {{ culture_dedup_order() }}) as rn
        from list_bronze
        where facility_id is not null
    ) where rn = 1
),

detail_bronze as (
    select
        json_extract_scalar(record_json, '$.mt10id')    as facility_id,
        json_extract_scalar(record_json, '$.adres')     as address_raw,
        json_extract_scalar(record_json, '$.la')        as lat_raw,   -- la = 위도
        json_extract_scalar(record_json, '$.lo')        as lon_raw,   -- lo = 경도
        json_extract_scalar(record_json, '$.seatscale') as seat_raw,  -- 총 좌석수(0 = 미상)
        ingest_ts, load_date, raw_object_key
    from {{ source('culture_bronze', 'bronze_kopis_facility_detail') }}
),

detail_latest as (
    select * from (
        select
            facility_id,
            nullif(trim(address_raw), '') as address,
            {{ asac_axes.seoul_lonlat('lon_raw', 'lat_raw') }},
            -- KOPIS 는 좌석수 미상을 0/공백으로 표기 → null 로 정규화(진짜 0석과 구분 없음, 둘 다 미측정 취급).
            nullif(try_cast(nullif(trim(seat_raw), '') as integer), 0) as seat_scale,
            row_number() over (partition by facility_id order by {{ culture_dedup_order() }}) as rn
        from detail_bronze
        where facility_id is not null
    ) where rn = 1
),

joined as (
    select
        l.facility_id, l.facility_name, l.sido, l.gu,
        d.address, d.longitude, d.latitude, d.seat_scale,
        l.source_system, l.dag_run_id, l.raw_object_key, l.collected_at, l.ingested_at, l.load_date
    from list_latest l
    left join detail_latest d on d.facility_id = l.facility_id
),

dong_map as {{ culture_dong_map('joined') }},

{{ culture_admin_canon() }}

select
    j.facility_id,
    j.facility_name,
    j.sido,
    j.address,
    j.longitude,
    j.latitude,
    j.gu,
    coalesce(cd.gu_code, cg.gu_code, d.coord_gu_code) as gu_code,
    coalesce(cd.admin_dong, d.admin_dong) as admin_dong,
    d.admin_dong_code,
    j.seat_scale,
    j.source_system, j.dag_run_id, j.raw_object_key, j.collected_at, j.ingested_at, j.load_date
from joined j
left join dong_map d on j.longitude = d.longitude and j.latitude = d.latitude
left join canon cd on cd.admin_dong_code = d.admin_dong_code
left join canon_gu cg on cg.gu = j.gu
