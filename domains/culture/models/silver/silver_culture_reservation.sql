-- silver: 공공예약 일 스냅샷 fact (culture+sport union). 그레인 = (service_id, load_date) —
-- 그날의 서비스 상태. 같은 날 재적재/페이지 겹침(7/1 실증 44행)은 dedup 이 흡수.

with unioned as (
    select 'culture' as reservation_type, record_json, ingest_ts,
           {{ culture_lineage('seoul') }}
    from {{ source('culture_bronze', 'bronze_seoul_culture_reservation') }}
    union all
    select 'sport' as reservation_type, record_json, ingest_ts,
           {{ culture_lineage('seoul') }}
    from {{ source('culture_bronze', 'bronze_seoul_sports_reservation') }}
),

typed as (
    select
        reservation_type,
        json_extract_scalar(record_json, '$.SVCID') as service_id,
        nullif(trim(json_extract_scalar(record_json, '$.SVCNM')), '')      as service_name,
        nullif(trim(json_extract_scalar(record_json, '$.AREANM')), '')     as gu,
        nullif(trim(json_extract_scalar(record_json, '$.SVCSTATNM')), '')  as status,
        nullif(trim(json_extract_scalar(record_json, '$.MINCLASSNM')), '') as category,
        nullif(trim(json_extract_scalar(record_json, '$.PLACENM')), '')    as place,
        nullif(trim(json_extract_scalar(record_json, '$.PAYATNM')), '')    as pay_type,
        {{ asac_axes.seoul_lonlat("json_extract_scalar(record_json, '$.X')", "json_extract_scalar(record_json, '$.Y')") }},
        ingest_ts, source_system, dag_run_id, raw_object_key, collected_at, ingested_at, load_date
    from unioned
    where json_extract_scalar(record_json, '$.SVCID') is not null
),

latest as (
    select * from (
        select *, row_number() over (
            partition by service_id, load_date
            order by {{ culture_dedup_order() }}
        ) as rn
        from typed
    ) where rn = 1
),

dong_map as {{ culture_dong_map('latest') }},

{{ culture_admin_canon() }}

select
    l.service_id, l.reservation_type, l.service_name, l.status, l.category, l.place, l.pay_type,
    cast(try(cast(l.load_date as date)) as timestamp(6)) as event_at,   -- 스냅샷 대표 시각
    l.longitude, l.latitude, l.gu,
    coalesce(cd.gu_code, cg.gu_code, d.coord_gu_code) as gu_code,
    coalesce(cd.admin_dong, d.admin_dong) as admin_dong, d.admin_dong_code,
    l.source_system, l.dag_run_id, l.raw_object_key, l.collected_at, l.ingested_at, l.load_date
from latest l
left join dong_map d on l.longitude = d.longitude and l.latitude = d.latitude
left join canon cd on cd.admin_dong_code = d.admin_dong_code
left join canon_gu cg on cg.gu = l.gu
