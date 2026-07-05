-- 인허가 현재 상태(업소당 최신 1행). history 의 암묵 버저닝 정렬
-- (updatedt_sort, lastmodts_sort, observed_date, collected_at, content_hash) 내림차순 최상위.
-- grain: (dataset, mgtno). 좌표 보정 조인(bronze_geocode_address)은 Step 8 에서 추가.

with ranked as (
    select
        *,
        row_number() over (
            partition by dataset, mgtno
            order by updatedt_sort desc, lastmodts_sort desc,
                     observed_date desc, collected_at desc, content_hash desc
        ) as recency_rank
    from {{ ref('silver_license_history') }}
)

select
    dataset,
    mgtno,
    bplcnm,
    trdstategbn,
    trdstatenm,
    dtlstategbn,
    dtlstatenm,
    apvpermymd,
    dcbymd,
    sitetel,
    road_address,
    jibun_address,
    road_address_norm,
    jibun_address_norm,
    district,
    address_key_road,
    address_key_jibun,
    source_coord_x,
    source_coord_y,
    content_hash,
    updatedt,
    updatedt_ts,
    lastmodts,
    lastmodts_ts,
    observed_date,
    collected_at,
    bronze_run_id,
    dag_run_id,
    raw_object_key,
    load_date
from ranked
where recency_rank = 1
