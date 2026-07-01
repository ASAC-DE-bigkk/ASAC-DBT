-- silver: 서울시립미술관 전시(ListExhibitionOfSeoulMOAInfo).
-- 분관명(DP_PLACE)→자치구 매핑은 seed 마스터(sema_branch_gu)의 keyword 부분일치 +
-- 우선순위(priority) 최상위 1건으로 결정. 미매핑(기타·서울 외·빈값)은 NULL → gold 제외.
-- (분관 추가/수정은 seeds/sema_branch_gu.csv 한 줄로.) 날짜 'YYYY-MM-DD'.

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
        ingest_ts
    from bronze
    where exhibition_id is not null
),

dedup as (
    select *, row_number() over (partition by exhibition_id order by ingest_ts desc) as rn
    from typed
),

latest as (select * from dedup where rn = 1),

-- 분관 keyword → 자치구 (seed 마스터). venue_name 부분일치 중 우선순위 최상위 1건.
gu_match as (
    select
        l.exhibition_id,
        s.location_key,
        row_number() over (
            partition by l.exhibition_id
            order by s.priority desc, s.location_key
        ) as pr
    from latest l
    join {{ ref('sema_branch_gu') }} s
        on l.venue_name like '%' || s.keyword || '%'
),

best_gu as (select exhibition_id, location_key from gu_match where pr = 1)

select
    l.exhibition_id,
    l.title,
    l.venue_name,
    g.location_key,          -- 자치구 (미매핑은 NULL → gold 제외)
    l.period_start,
    l.period_end
from latest l
left join best_gu g on l.exhibition_id = g.exhibition_id
