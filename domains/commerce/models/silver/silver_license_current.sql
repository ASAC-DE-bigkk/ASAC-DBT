-- 인허가 현재 상태(업소당 최신 1버전). history 의 is_current 슬라이스.
-- grain: (dataset, mgtno). 좌표 보정 조인(bronze_geocode_address)은 Step 8 에서 추가.

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
    valid_from,
    version_seq,
    observed_date,
    collected_at,
    bronze_run_id,
    dag_run_id,
    raw_object_key,
    load_date
from {{ ref('silver_license_history') }}
where is_current
