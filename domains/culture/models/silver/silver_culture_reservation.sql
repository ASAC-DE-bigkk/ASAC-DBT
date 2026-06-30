-- silver: 공공서비스예약(문화 + 체육) 스냅샷. 상태(SVCSTATNM)·자치구(AREANM) 보유.
-- 스냅샷형: (SVCID, load_date)당 1행 = 그 날의 예약 서비스 상태. 같은 날 재적재는 최신 ingest_ts.
-- 명시적 충원율 필드 없음 → 상태로 가용률(접수중 비율)을 gold에서 계산.

with raw as (
    select 'culture' as reservation_type, record_json, load_date, ingest_ts
    from {{ source('culture_bronze', 'bronze_seoul_culture_reservation') }}
    union all
    select 'sport' as reservation_type, record_json, load_date, ingest_ts
    from {{ source('culture_bronze', 'bronze_seoul_sports_reservation') }}
),

parsed as (
    select
        json_extract_scalar(record_json, '$.SVCID')      as service_id,
        reservation_type,
        nullif(trim(json_extract_scalar(record_json, '$.SVCNM')), '')     as service_name,
        nullif(trim(json_extract_scalar(record_json, '$.AREANM')), '')    as location_key,   -- 자치구
        nullif(trim(json_extract_scalar(record_json, '$.SVCSTATNM')), '') as status,
        nullif(trim(json_extract_scalar(record_json, '$.MINCLASSNM')), '') as category,
        nullif(trim(json_extract_scalar(record_json, '$.PLACENM')), '')   as place,
        nullif(trim(json_extract_scalar(record_json, '$.PAYATNM')), '')   as pay_type,
        load_date,
        ingest_ts
    from raw
    where json_extract_scalar(record_json, '$.SVCID') is not null
),

dedup as (
    -- 스냅샷 단위 중복제거: 같은 서비스·같은 날이면 최신 적재만.
    select *, row_number() over (partition by service_id, load_date order by ingest_ts desc) as rn
    from parsed
)

select
    service_id,
    reservation_type,
    service_name,
    location_key,
    status,
    category,
    place,
    pay_type,
    load_date,
    ingest_ts
from dedup
where rn = 1
