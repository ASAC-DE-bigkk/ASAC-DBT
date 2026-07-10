-- silver: KCISA 한눈에보는문화정보 서울 행사 fact — 전 serviceName 편입(#85).
-- 그레인 event_id(=seq). 좌표 내장(gpsX=경도, gpsY=위도) → 행정동 직접 매핑.
-- 3축 anti-join dedup: 기존 축(performance·event·exhibition)이 정본 —
-- 정규화 제목 일치 + (기간 교차 or 한쪽 null)이면 KCISA 행을 버린다(보강 소스).
-- 기간 조건이 재공연(같은 제목·다른 시기)을 살린다(설계 §dedup, perf 102→97 실측).

with bronze as (
    select
        json_extract_scalar(record_json, '$.seq')         as event_id_raw,
        json_extract_scalar(record_json, '$.title')       as title_raw,
        json_extract_scalar(record_json, '$.place')       as place_raw,
        json_extract_scalar(record_json, '$.serviceName') as service_raw,
        json_extract_scalar(record_json, '$.realmName')   as realm_raw,
        json_extract_scalar(record_json, '$.sigungu')     as gu_raw,
        json_extract_scalar(record_json, '$.startDate')   as start_raw,
        json_extract_scalar(record_json, '$.endDate')     as end_raw,
        json_extract_scalar(record_json, '$.gpsX')        as lon_raw,   -- 경도
        json_extract_scalar(record_json, '$.gpsY')        as lat_raw,   -- 위도
        ingest_ts,
        {{ culture_lineage('kcisa') }}
    from {{ source('culture_bronze', 'bronze_kcisa_seoul_event') }}
),

typed as (
    select
        event_id_raw as event_id,
        nullif(trim(title_raw), '')   as title,
        nullif(trim(place_raw), '')   as venue_name,
        nullif(trim(service_raw), '') as service_name,
        nullif(trim(realm_raw), '')   as category,
        nullif(trim(gu_raw), '')      as gu,
        try(cast(date_parse(start_raw, '%Y%m%d') as date)) as event_start_date,
        try(cast(date_parse(end_raw, '%Y%m%d') as date))   as event_end_date,
        {{ asac_axes.seoul_lonlat('lon_raw', 'lat_raw') }},
        ingest_ts, source_system, dag_run_id, raw_object_key, collected_at, ingested_at, load_date
    from bronze
    where event_id_raw is not null
      and nullif(trim(title_raw), '') is not null
),

latest as (
    select * from (
        select *, row_number() over (partition by event_id order by {{ culture_dedup_order() }}) as rn
        from typed
    ) where rn = 1
),

normed as (
    select *, {{ culture_norm_title('title') }} as norm_title
    from latest
),

deduped as (
    select n.* from normed n
    where not exists (
        select 1 from {{ ref('silver_culture_performance') }} p
        where {{ culture_norm_title('p.performance_name') }} = n.norm_title
          and (p.event_start_date is null or p.event_end_date is null
               or n.event_start_date is null or n.event_end_date is null
               or (p.event_start_date <= n.event_end_date and p.event_end_date >= n.event_start_date))
    )
    and not exists (
        select 1 from {{ ref('silver_culture_event') }} e
        where {{ culture_norm_title('e.event_title') }} = n.norm_title
          and (e.event_start_date is null or e.event_end_date is null
               or n.event_start_date is null or n.event_end_date is null
               or (e.event_start_date <= n.event_end_date and e.event_end_date >= n.event_start_date))
    )
    and not exists (
        select 1 from {{ ref('silver_culture_exhibition') }} x
        where x.title is not null
          and {{ culture_norm_title('x.title') }} = n.norm_title
          and (x.event_start_date is null or x.event_end_date is null
               or n.event_start_date is null or n.event_end_date is null
               or (x.event_start_date <= n.event_end_date and x.event_end_date >= n.event_start_date))
    )
),

dong_map as {{ culture_dong_map('deduped') }},

{{ culture_admin_canon() }}

select
    d.event_id, d.title, d.venue_name, d.service_name, d.category,
    d.event_start_date, d.event_end_date,
    cast(d.event_start_date as timestamp(6)) as event_at,
    d.longitude, d.latitude, d.gu,
    coalesce(cd.gu_code, cg.gu_code, m.coord_gu_code) as gu_code,
    coalesce(cd.admin_dong, m.admin_dong) as admin_dong, m.admin_dong_code,
    d.source_system, d.dag_run_id, d.raw_object_key, d.collected_at, d.ingested_at, d.load_date
from deduped d
left join dong_map m on d.longitude = m.longitude and d.latitude = m.latitude
left join canon cd on cd.admin_dong_code = m.admin_dong_code
left join canon_gu cg on cg.gu = d.gu
