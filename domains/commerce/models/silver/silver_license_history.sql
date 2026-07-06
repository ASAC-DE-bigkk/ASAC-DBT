-- 인허가 변경 이력(정제된 변경로그). bronze 변경로그 → publishable run 필터 → 파싱/파생 →
-- 연속 중복 제거(diff 재유입·reconcile 재방출 제거, 정당한 원복 A→B→A 보존).
-- 명시적 버전 컬럼(version_seq/valid_from/valid_to/is_current) 없음 — (dataset, mgtno) 안에서
-- (updatedt_sort, lastmodts_sort, observed_date, collected_at, content_hash) 내림차순 정렬이
-- 곧 버전 순서다(암묵 버저닝). current 는 이 정렬의 최신 1행.
-- 타임존 정책: silver 의 timestamp 는 **전부 KST(naive)** — KST 원문(UPDATEDT/LASTMODTS)은
-- 문자열로 보존하고 *_ts 는 파싱만(무변환, KST), collected_at 은 bronze 의 UTC 값을 +9h 하여 KST 로 변환.
-- (bronze 는 UTC 원본을 그대로 유지 = 소스 진실; KST 일원화는 silver 표기 계층에서만.)
-- 상세/결측 규약: docs/timestamps-and-nulls.md · 컬럼 구조: docs/dataset-columns.md

with publishable as (
    -- 데이터셋별 발행 게이트: is_publishable 인 (dataset, bronze_run_id) 만 반영.
    select distinct
        cast(dataset as varchar) as dataset,
        cast(bronze_run_id as varchar) as bronze_run_id
    from {{ source('commerce_bronze', 'collection_run_manifest') }}
    where status = 'SUCCESS'
      and is_publishable
),

bronze as (
    select
        cast(b.dataset as varchar) as dataset,
        cast(b.mgtno as varchar) as mgtno,
        cast(b.record_json as varchar) as record_json,
        cast(b.content_hash as varchar) as content_hash,
        cast(b.updatedt as varchar) as updatedt,
        cast(b.observed_date as varchar) as observed_date,
        cast(b.load_date as varchar) as load_date,
        cast(b.bronze_run_id as varchar) as bronze_run_id,
        cast(b.dag_run_id as varchar) as dag_run_id,
        cast(b.raw_object_key as varchar) as raw_object_key,
        -- bronze 는 수집 시점을 UTC 로 기록(_utcnow_iso). silver 는 KST 일원화 → +9h 로 변환.
        -- (한국은 DST 없음 — 고정 오프셋. bronze 원본은 UTC 유지, 여기서만 표기 변환.)
        cast(b.collected_at as timestamp(6)) + interval '9' hour as collected_at
    from {{ source('commerce_bronze', 'localdata_license') }} as b
    inner join publishable as p
        on cast(b.dataset as varchar) = p.dataset
        and cast(b.bronze_run_id as varchar) = p.bronze_run_id
    -- 단위 제외(삭제) — vars 목록 기반. 정책: docs/rebuild-and-ops.md
    where 1 = 1
        {{ not_in_excluded("cast(b.dataset as varchar)", 'exclude_datasets') }}
        {{ not_in_excluded("cast(b.observed_date as varchar)", 'exclude_observed_dates') }}
        {{ not_in_excluded("cast(b.load_date as varchar)", 'exclude_load_dates') }}
        {{ not_in_excluded("cast(b.bronze_run_id as varchar)", 'exclude_bronze_run_ids') }}
),

parsed as (
    select
        *,
        -- 결측 규약 v1: 원본 '' → null (nullif+trim). 원본 그대로는 record_json 에 보존.
        nullif(trim(json_extract_scalar(record_json, '$.BPLCNM')), '') as bplcnm,
        nullif(trim(json_extract_scalar(record_json, '$.TRDSTATEGBN')), '') as trdstategbn,
        nullif(trim(json_extract_scalar(record_json, '$.TRDSTATENM')), '') as trdstatenm,
        nullif(trim(json_extract_scalar(record_json, '$.DTLSTATEGBN')), '') as dtlstategbn,
        nullif(trim(json_extract_scalar(record_json, '$.DTLSTATENM')), '') as dtlstatenm,
        nullif(trim(json_extract_scalar(record_json, '$.APVPERMYMD')), '') as apvpermymd,
        nullif(trim(json_extract_scalar(record_json, '$.DCBYMD')), '') as dcbymd,
        nullif(trim(json_extract_scalar(record_json, '$.SITETEL')), '') as sitetel,
        nullif(trim(json_extract_scalar(record_json, '$.SITEWHLADDR')), '') as jibun_address,
        nullif(trim(json_extract_scalar(record_json, '$.RDNWHLADDR')), '') as road_address,
        nullif(trim(json_extract_scalar(record_json, '$.X')), '') as source_coord_x,
        nullif(trim(json_extract_scalar(record_json, '$.Y')), '') as source_coord_y,
        nullif(trim(json_extract_scalar(record_json, '$.LASTMODTS')), '') as lastmodts,
        -- UPDATEDT(KST 문자열, 14자리 기대, 비정형 가능) → **KST** timestamp(파싱만·무변환). 실패 시 null.
        try(date_parse(
            substr(regexp_replace(updatedt, '[^0-9]', ''), 1, 14), '%Y%m%d%H%i%s'
        )) as updatedt_ts
    from bronze
),

normalized as (
    select
        *,
        -- LASTMODTS(KST 문자열, 'YYYY-MM-DD HH:MM:SS' 계열 기대, 비정형 가능) → **KST** timestamp(파싱만·무변환). 실패 시 null.
        try(date_parse(
            substr(regexp_replace(lastmodts, '[^0-9]', ''), 1, 14), '%Y%m%d%H%i%s'
        )) as lastmodts_ts,
        -- 주소 정규화 v1: '(' 이후 절단 → 연속 공백 1개 → trim → 빈값 null. (Python 수집측과 규칙 동일)
        nullif(trim(regexp_replace(regexp_replace(coalesce(road_address, ''), '\(.*$', ''), '\s+', ' ')), '') as road_address_norm,
        nullif(trim(regexp_replace(regexp_replace(coalesce(jibun_address, ''), '\(.*$', ''), '\s+', ' ')), '') as jibun_address_norm,
        -- 자치구(구) 파생 — 도로명 우선, 지번 폴백. 서울 외/미매칭은 null.
        regexp_extract(
            coalesce(road_address, jibun_address, ''), '서울특별시\s+(\S+구)', 1
        ) as district
    from parsed
),

keyed as (
    select
        *,
        -- geocode 조인 키(§4.5) — Step 8 에서 bronze_geocode_address 와 조인. 도로명/지번 2종.
        case when road_address_norm is not null
             then lower(to_hex(sha256(cast(road_address_norm as varbinary)))) end as address_key_road,
        case when jibun_address_norm is not null
             then lower(to_hex(sha256(cast(jibun_address_norm as varbinary)))) end as address_key_jibun,
        -- 전순서 버전 정렬키: UPDATEDT → LASTMODTS → 관측일 → 수집시각 → content_hash(항상 tie-break).
        -- 결측 timestamp 는 epoch(가장 오래된 것) 취급 — 시각 해석엔 *_ts 를 쓸 것(정렬 전용).
        coalesce(updatedt_ts, timestamp '1970-01-01 00:00:00') as updatedt_sort,
        coalesce(lastmodts_ts, timestamp '1970-01-01 00:00:00') as lastmodts_sort
    from normalized
),

ordered as (
    select
        *,
        lag(content_hash) over (
            partition by dataset, mgtno
            order by updatedt_sort, lastmodts_sort, observed_date, collected_at, content_hash
        ) as prev_content_hash
    from keyed
),

-- 연속(인접) 중복만 제거 → diff 재유입/reconcile 재방출은 걸러내고 정당한 원복(A→B→A)은 보존.
-- 동일 content 재방출은 UPDATEDT/LASTMODTS 도 동일(해시가 두 필드를 포함)이라 항상 인접 정렬된다.
deduped as (
    select *
    from ordered
    where prev_content_hash is null
       or prev_content_hash <> content_hash
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
    updatedt_sort,
    lastmodts,
    lastmodts_ts,
    lastmodts_sort,
    observed_date,
    collected_at,
    bronze_run_id,
    dag_run_id,
    raw_object_key,
    load_date
from deduped
