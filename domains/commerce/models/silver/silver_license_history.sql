-- 인허가 SCD2 이력. bronze 변경로그 → publishable run 필터 → 파싱/파생 →
-- 연속 중복 제거(A→B→A 원복 보존) → 버전 정렬 → valid_from/valid_to/is_current.
-- 설계: dags/domains/commerce/docs/pipeline/medallion-implementation-plan.md §2.2

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
        cast(b.collected_at as timestamp(6)) as collected_at
    from {{ source('commerce_bronze', 'localdata_license') }} as b
    inner join publishable as p
        on cast(b.dataset as varchar) = p.dataset
        and cast(b.bronze_run_id as varchar) = p.bronze_run_id
),

parsed as (
    select
        *,
        json_extract_scalar(record_json, '$.BPLCNM') as bplcnm,
        json_extract_scalar(record_json, '$.TRDSTATEGBN') as trdstategbn,
        json_extract_scalar(record_json, '$.TRDSTATENM') as trdstatenm,
        json_extract_scalar(record_json, '$.DTLSTATEGBN') as dtlstategbn,
        json_extract_scalar(record_json, '$.DTLSTATENM') as dtlstatenm,
        json_extract_scalar(record_json, '$.APVPERMYMD') as apvpermymd,
        json_extract_scalar(record_json, '$.DCBYMD') as dcbymd,
        json_extract_scalar(record_json, '$.SITETEL') as sitetel,
        json_extract_scalar(record_json, '$.SITEWHLADDR') as jibun_address,
        json_extract_scalar(record_json, '$.RDNWHLADDR') as road_address,
        json_extract_scalar(record_json, '$.X') as source_coord_x,
        json_extract_scalar(record_json, '$.Y') as source_coord_y,
        -- UPDATEDT(14자리 YYYYMMDDHHMMSS 기대, 비정형 가능) → timestamp. 실패 시 null.
        try(date_parse(
            substr(regexp_replace(updatedt, '[^0-9]', ''), 1, 14), '%Y%m%d%H%i%s'
        )) as updatedt_ts
    from bronze
),

normalized as (
    select
        *,
        -- 주소 정규화 v1: '(' 이후 절단 → 연속 공백 1개 → trim → 빈값 null. (Python 수집측과 규칙 동일)
        nullif(trim(regexp_replace(regexp_replace(coalesce(road_address, ''), '\(.*$', ''), '\s+', ' ')), '') as road_address_norm,
        nullif(trim(regexp_replace(regexp_replace(coalesce(jibun_address, ''), '\(.*$', ''), '\s+', ' ')), '') as jibun_address_norm,
        -- 자치구(구) 파생 — 도로명 우선, 지번 폴백. 서울 외/미매칭은 null.
        regexp_extract(
            coalesce(nullif(road_address, ''), jibun_address, ''), '서울특별시\s+(\S+구)', 1
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
        -- 전순서 버전 정렬키(§2.2): UPDATEDT → 관측일 → 수집시각 → content_hash(항상 tie-break).
        coalesce(updatedt_ts, timestamp '1970-01-01 00:00:00') as version_ts
    from normalized
),

ordered as (
    select
        *,
        lag(content_hash) over (
            partition by dataset, mgtno
            order by version_ts, observed_date, collected_at, content_hash
        ) as prev_content_hash
    from keyed
),

-- 연속(인접) 중복만 제거 → diff 재유입/reconcile 재방출은 걸러내고 정당한 원복(A→B→A)은 보존.
deduped as (
    select *
    from ordered
    where prev_content_hash is null
       or prev_content_hash <> content_hash
),

versioned as (
    select
        *,
        row_number() over (
            partition by dataset, mgtno
            order by version_ts, observed_date, collected_at, content_hash
        ) as version_seq
    from deduped
),

scd2 as (
    select
        *,
        coalesce(updatedt_ts, collected_at) as valid_from,
        lead(coalesce(updatedt_ts, collected_at)) over (
            partition by dataset, mgtno order by version_seq
        ) as valid_to
    from versioned
)

select
    dataset,
    mgtno,
    version_seq,
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
    valid_to,
    (valid_to is null) as is_current,
    observed_date,
    collected_at,
    bronze_run_id,
    dag_run_id,
    raw_object_key,
    load_date
from scd2
