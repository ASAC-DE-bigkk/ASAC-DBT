-- silver: run×dataset 그레인. run_report datasets[] 를 UNNEST — 병목 추이(duration_sec)의 원천.
-- 공간축 면제. UNNEST 관용구는 citydata(silver_citydata_cmrcl_rsb) 차용. rows→row_count(예약어 회피).
{{ config(tags=['slo']) }}

with bronze as (
    select
        json_extract_scalar(record_json, '$.domain') as domain,
        run_id,
        load_date,
        record_json
    from {{ source('culture_bronze', 'bronze_culture_run_report') }}
),

exploded as (
    select
        b.domain,
        b.run_id,
        b.load_date,
        ds
    from bronze b
    cross join unnest(
        cast(json_extract(b.record_json, '$.datasets') as array(json))
    ) as t(ds)
),

typed as (
    select
        domain,
        run_id,
        load_date,
        json_extract_scalar(ds, '$.name')                                  as dataset_name,
        json_extract_scalar(ds, '$.source')                                as source,
        json_extract_scalar(ds, '$.endpoint')                              as endpoint,
        try(cast(json_extract_scalar(ds, '$.rows') as bigint))             as row_count,
        try(cast(json_extract_scalar(ds, '$.pages') as integer))           as pages,
        try(cast(json_extract_scalar(ds, '$.bytes') as bigint))            as bytes,
        try(cast(json_extract_scalar(ds, '$.duration_sec') as double))     as duration_sec,
        try(cast(json_extract_scalar(ds, '$.iceberg_rows') as bigint))     as iceberg_rows,
        json_extract_scalar(ds, '$.finished_ts')                           as finished_ts_raw,
        nullif(json_extract_scalar(ds, '$.error'), '')                     as error,
        coalesce(try(cast(json_extract_scalar(ds, '$.checks.passed') as boolean)), false) as dataset_passed
    from exploded
)

select
    domain,
    run_id,
    load_date,
    dataset_name,
    source,
    endpoint,
    row_count,
    pages,
    bytes,
    duration_sec,
    iceberg_rows,
    {{ asac_axes.utc_to_kst("try(cast(date_parse(finished_ts_raw, '%Y%m%dT%H%i%sZ') as timestamp(6)))") }} as finished_at,
    error,
    dataset_passed
from typed
