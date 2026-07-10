-- silver: 시립미술관 전시 기간 fact. 위치는 sema_branch_location seed 키워드 매칭 —
-- 분관(priority 10)만 좌표 보유 → 동 레벨은 분관 전시만, 그 외 구 레벨(설계 §4).

with bronze as (
    select
        json_extract_scalar(record_json, '$.DP_EX_NO') as exhibition_id,
        json_extract_scalar(record_json, '$.DP_NAME')  as title_raw,
        json_extract_scalar(record_json, '$.DP_PLACE') as venue_raw,
        json_extract_scalar(record_json, '$.DP_START') as start_raw,
        json_extract_scalar(record_json, '$.DP_END')   as end_raw,
        ingest_ts,
        {{ culture_lineage('seoul') }}
    from {{ source('culture_bronze', 'bronze_seoul_sema_exhibition') }}
),

latest as (
    select * from (
        select
            exhibition_id,
            nullif(trim(title_raw), '') as title,
            nullif(trim(venue_raw), '') as venue_name,
            try(cast(substr(start_raw, 1, 10) as date)) as event_start_date,
            try(cast(substr(end_raw, 1, 10) as date))   as event_end_date,
            source_system, dag_run_id, raw_object_key, collected_at, ingested_at, load_date,
            row_number() over (partition by exhibition_id order by {{ culture_dedup_order() }}) as rn
        from bronze
        where exhibition_id is not null
    ) where rn = 1
),

matched as (
    select
        l.exhibition_id,
        s.gu, s.latitude, s.longitude,
        row_number() over (
            partition by l.exhibition_id
            order by s.priority desc, s.keyword
        ) as pr
    from latest l
    join {{ ref('sema_branch_location') }} s on strpos(l.venue_name, s.keyword) > 0
),

best as (select exhibition_id, gu, latitude, longitude from matched where pr = 1),

placed as (
    select
        l.exhibition_id, l.title, l.venue_name,
        l.event_start_date, l.event_end_date,
        b.gu, b.latitude, b.longitude,
        l.source_system, l.dag_run_id, l.raw_object_key, l.collected_at, l.ingested_at, l.load_date
    from latest l
    left join best b on b.exhibition_id = l.exhibition_id
),

dong_map as {{ culture_dong_map('placed') }},

{{ culture_admin_canon() }}

select
    p.exhibition_id, p.title, p.venue_name,
    p.event_start_date, p.event_end_date,
    cast(p.event_start_date as timestamp(6)) as event_at,
    p.longitude, p.latitude, p.gu,
    coalesce(cd.gu_code, cg.gu_code, d.coord_gu_code) as gu_code,
    coalesce(cd.admin_dong, d.admin_dong) as admin_dong, d.admin_dong_code,
    p.source_system, p.dag_run_id, p.raw_object_key, p.collected_at, p.ingested_at, p.load_date
from placed p
left join dong_map d on p.longitude = d.longitude and p.latitude = d.latitude
left join canon cd on cd.admin_dong_code = d.admin_dong_code
left join canon_gu cg on cg.gu = p.gu
