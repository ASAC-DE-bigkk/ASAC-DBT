-- silver: 서울시립미술관 전시(ListExhibitionOfSeoulMOAInfo).
-- 분관명(DP_PLACE)→자치구 매핑(주요 분관만 확정, 그 외 NULL=gold 제외). 날짜 'YYYY-MM-DD'.
-- (분관→자치구 마스터 dim/seed는 후속 — 지금은 확실한 주요 분관만 CASE)

with bronze as (
    select
        json_extract_scalar(record_json, '$.DP_EX_NO') as exhibition_id,
        json_extract_scalar(record_json, '$.DP_NAME')  as title,
        json_extract_scalar(record_json, '$.DP_PLACE') as venue_name,
        json_extract_scalar(record_json, '$.DP_START') as strt_raw,
        json_extract_scalar(record_json, '$.DP_END')   as end_raw,
        ingest_ts
    from {{ source('culture_bronze', 'bronze_seoul_sema_exhibition') }}
),

typed as (
    select
        exhibition_id,
        nullif(trim(title), '')      as title,
        nullif(trim(venue_name), '') as venue_name,
        try(cast(substr(strt_raw, 1, 10) as date)) as period_start,
        try(cast(substr(end_raw, 1, 10) as date))  as period_end,
        case
            when venue_name like '%서소문본관%'   then '중구'
            when venue_name like '%북서울%'       then '노원구'
            when venue_name like '%난지%'         then '마포구'
            when venue_name like '%남서울%'       then '관악구'
            when venue_name like '%SeMA 창고%'    then '은평구'
            when venue_name like '%벙커%'         then '영등포구'
            when venue_name like '%사진미술관%'   then '도봉구'
            when venue_name like '%미술아카이브%' then '종로구'
            when venue_name like '%서서울%'       then '금천구'
            else null
        end as location_key,   -- 자치구 (미매핑은 NULL → gold 제외)
        ingest_ts
    from bronze
    where exhibition_id is not null
),

dedup as (
    select *, row_number() over (partition by exhibition_id order by ingest_ts desc) as rn
    from typed
)

select
    exhibition_id,
    title,
    venue_name,
    location_key,
    period_start,
    period_end
from dedup
where rn = 1
