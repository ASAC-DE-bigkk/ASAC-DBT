-- silver: 서울 문화행사 기간 fact. 자연키 부재 → event_key = md5(제목|시작일|장소) —
-- 제목 수정 시 분열은 알려진 한계(설계 §3-G). 좌표: LOT=경도, LAT=위도.
-- dedup 은 load_date 우선(§3-A) — 7/1 proxy(ingest_ts=7/6 수동)가 이후 관측을 못 가림.

with bronze as (
    select
        json_extract_scalar(record_json, '$.TITLE')    as title_raw,
        json_extract_scalar(record_json, '$.GUNAME')   as gu_raw,
        json_extract_scalar(record_json, '$.PLACE')    as place_raw,
        json_extract_scalar(record_json, '$.CODENAME') as category,
        json_extract_scalar(record_json, '$.IS_FREE')  as is_free,
        json_extract_scalar(record_json, '$.STRTDATE') as start_raw,
        json_extract_scalar(record_json, '$.END_DATE') as end_raw,
        json_extract_scalar(record_json, '$.LOT')      as lon_raw,   -- 경도
        json_extract_scalar(record_json, '$.LAT')      as lat_raw,   -- 위도
        ingest_ts,
        {{ culture_lineage('seoul') }}
    from {{ source('culture_bronze', 'bronze_seoul_cultural_event') }}
),

typed as (
    select
        nullif(trim(title_raw), '') as event_title,
        nullif(trim(gu_raw), '')    as gu,
        nullif(trim(place_raw), '') as place,
        nullif(trim(category), '')  as category,
        nullif(trim(is_free), '')   as is_free,
        try(cast(substr(start_raw, 1, 10) as date)) as event_start_date,
        try(cast(substr(end_raw, 1, 10) as date))   as event_end_date,
        {{ asac_axes.seoul_lonlat('lon_raw', 'lat_raw') }},
        ingest_ts, source_system, dag_run_id, raw_object_key, collected_at, ingested_at, load_date
    from bronze
    where nullif(trim(title_raw), '') is not null
),

keyed as (
    select
        to_hex(md5(to_utf8(concat_ws('|',
            coalesce(event_title, ''),
            coalesce(cast(event_start_date as varchar), ''),
            coalesce(place, ''))))) as event_key,
        typed.*
    from typed
),

latest as (
    select * from (
        select *, row_number() over (partition by event_key order by {{ culture_dedup_order() }}) as rn
        from keyed
    ) where rn = 1
),

dong_map as {{ culture_dong_map('latest') }},

{{ culture_admin_canon() }},

stamped as (
select
    l.event_key, l.event_title, l.place, l.category, l.is_free,
    l.event_start_date, l.event_end_date,
    cast(l.event_start_date as timestamp(6)) as event_at,
    l.longitude, l.latitude, l.gu,
    coalesce(cd.gu_code, cg.gu_code, d.coord_gu_code) as gu_code,
    coalesce(cd.admin_dong, d.admin_dong) as admin_dong, d.admin_dong_code,
    l.source_system, l.dag_run_id, l.raw_object_key, l.collected_at, l.ingested_at, l.load_date
from latest l
left join dong_map d on l.longitude = d.longitude and l.latitude = d.latitude
left join canon cd on cd.admin_dong_code = d.admin_dong_code
left join canon_gu cg on cg.gu = l.gu
)

select *, {{ culture_quality_status() }} as quality_status
from stamped
