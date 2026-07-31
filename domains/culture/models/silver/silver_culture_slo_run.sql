-- silver: run 그레인 SLO 성적표. 그레인 = run_id. 공간축 면제(관측 메타 — boxoffice 선례).
-- 핵심: slo_passed = raw AND expected>0 (초록 위장 교정, 설계 §1). 도메인 중립(domain 컬럼).
-- run_id/ingest_ts/load_date 는 bronze 컬럼(로더가 리포트값으로 stamp) — json 재추출 안 함.
{{ config(tags=['slo']) }}

with bronze as (
    select
        json_extract_scalar(record_json, '$.domain')                                     as domain,
        try(cast(json_extract_scalar(record_json, '$.coverage.expected') as integer))    as expected,
        try(cast(json_extract_scalar(record_json, '$.coverage.landed') as integer))      as landed,
        try(cast(json_extract_scalar(record_json, '$.coverage.skipped') as integer))     as skipped,
        try(cast(json_extract_scalar(record_json, '$.coverage.failed') as integer))      as failed,
        try(cast(json_extract_scalar(record_json, '$.coverage.coverage_pct') as double)) as coverage_pct,
        try(cast(json_extract_scalar(record_json, '$.total_rows') as bigint))            as total_rows,
        try(cast(json_extract_scalar(record_json, '$.total_iceberg_rows') as bigint))    as total_iceberg_rows,
        -- #619 확정안 필드. 2026-07-31 이전 리포트엔 없어 NULL 로 들어온다 — 그게 맞다
        -- ("그때는 안 남겼다"이지 "0 건"이 아니다). coalesce 로 메우면 안 된다.
        json_extract_scalar(record_json, '$.event_id')                                   as event_id,
        try(cast(json_extract_scalar(record_json, '$.record_count') as integer))         as record_count,
        -- rows_source 는 공통 계약(product-observability/v2)의 필드명 그대로 — 도메인을
        -- 모르는 조회 모델이 이 기록의 정본 행 수 출처를 한 곳에서 읽는다.
        json_extract_scalar(record_json, '$.rows_source')                                as rows_source,
        json_extract_scalar(record_json, '$.row_count_source.total_rows')                as total_rows_source,
        try(cast(json_extract_scalar(record_json, '$.iceberg_rows_measured') as integer)) as iceberg_rows_measured,
        coalesce(try(cast(json_extract_scalar(record_json, '$.load_failed') as boolean)), false)  as load_failed,
        try(cast(json_extract_scalar(record_json, '$.violation_count') as integer))      as violation_count,
        coalesce(try(cast(json_extract_scalar(record_json, '$.slo_passed') as boolean)), false)   as slo_passed_raw,
        run_id,
        ingest_ts,
        {{ culture_lineage('culture') }}
    from {{ source('culture_bronze', 'bronze_culture_run_report') }}
),

typed as (
    select
        domain,
        run_id,
        load_date,
        cast(load_date as timestamp(6))                    as event_at,
        ingest_ts,
        expected, landed, skipped, failed, coverage_pct,
        total_rows, total_iceberg_rows, load_failed, violation_count,
        event_id, record_count, rows_source, total_rows_source,
        iceberg_rows_measured,
        -- 관측 커버리지: 착지한 데이터셋 중 적재 행 수를 실제로 잰 비율. 100 미만이면
        -- 그 run 의 적재 수치는 '부분 관측'이다(#619 지표 — NULL 비율 축). 분모가 없거나
        -- (landed=0) 필드 자체가 없던 옛 리포트면 NULL — 0.0 으로 적으면 "0% 관측"이라는
        -- 측정 결과처럼 보인다. 여기에 coalesce 를 쓰면 7/31 이전 이력이 전부 0% 로 굳는다.
        case when iceberg_rows_measured is not null and coalesce(landed, 0) > 0
             then round(100.0 * cast(iceberg_rows_measured as double) / landed, 1)
        end                                                as iceberg_measure_pct,
        slo_passed_raw,
        (slo_passed_raw and coalesce(expected, 0) > 0)     as slo_passed,
        case
            when run_id like 'scheduled__%' then 'scheduled'
            when run_id like 'backfill%'    then 'backfill'
            else 'manual'
        end                                                as run_kind,
        raw_object_key,
        source_system, dag_run_id, collected_at, ingested_at
    from bronze
),

deduped as (
    select
        *,
        row_number() over (partition by run_id order by {{ culture_dedup_order() }}) as rn
    from typed
)

select
    domain,
    run_id,
    load_date,
    event_at,
    ingest_ts,
    expected, landed, skipped, failed, coverage_pct,
    total_rows, total_iceberg_rows, load_failed, violation_count,
    event_id, record_count, rows_source, total_rows_source,
    iceberg_rows_measured, iceberg_measure_pct,
    slo_passed_raw,
    slo_passed,
    run_kind,
    raw_object_key as report_object_key,
    source_system, dag_run_id, collected_at, ingested_at
from deduped
where rn = 1
