{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['place_id', 'nx', 'ny', 'base_date', 'base_time', 'category', 'fcst_date', 'fcst_time']
) }}

with publishable_runs as (
    select distinct cast(dag_run_id as varchar) as dag_run_id
    from {{ source('weather_bronze', 'collection_run_manifest') }}
    where source_id = 'kma_vilage_fcst'
      and status = 'SUCCESS'
      and is_publishable
),

bronze as (
    select
        cast(bronze.request_id as varchar) as request_id,
        cast(bronze.source_id as varchar) as source_id,
        cast(bronze.request_params_json as varchar) as request_params_json,
        cast(bronze.place_id as varchar) as place_id,
        cast(bronze.base_date as varchar) as base_date,
        cast(bronze.base_time as varchar) as base_time,
        cast(bronze.nx as integer) as nx,
        cast(bronze.ny as integer) as ny,
        cast(bronze.category as varchar) as category,
        cast(bronze.fcst_date as varchar) as fcst_date,
        cast(bronze.fcst_time as varchar) as fcst_time,
        cast(bronze.fcst_value as varchar) as fcst_value_raw,
        try_cast(bronze.fcst_value as double) as fcst_value_num,
        cast(bronze.raw_object_key as varchar) as raw_object_key,
        cast(bronze.payload_hash as varchar) as payload_hash,
        cast(bronze.result_code as varchar) as result_code,
        cast(bronze.result_msg as varchar) as result_msg,
        cast(bronze.total_count as integer) as total_count,
        cast(bronze.item_count as integer) as item_count,
        cast(bronze.collected_at as timestamp(6)) as collected_at,
        cast(bronze.load_date as varchar) as load_date,
        cast(bronze.dag_run_id as varchar) as dag_run_id
    from {{ source('weather_bronze', 'kma_vilage_fcst') }} as bronze
    inner join publishable_runs
        on cast(bronze.dag_run_id as varchar) = publishable_runs.dag_run_id
    {% if is_incremental() %}
    where cast(bronze.collected_at as timestamp(6)) >= (
        select coalesce(max(collected_at), timestamp '1970-01-01') - interval '30' minute
        from {{ this }}
    )
    {% endif %}
),

standardized as (
    select
        *,
        {{ asac_axes.kst_at_from_parts('base_date', 'base_time') }} as issued_at,
        {{ asac_axes.kst_at_from_parts('fcst_date', 'fcst_time') }} as forecast_at
    from bronze
    where result_code = '00'
),

ranked as (
    select
        *,
        row_number() over (
            partition by place_id, nx, ny, base_date, base_time, category, fcst_date, fcst_time
            order by collected_at desc, raw_object_key desc, request_id desc
        ) as row_num
    from standardized
    where issued_at is not null
      and forecast_at is not null
)

select
    request_id,
    source_id,
    request_params_json,
    place_id,
    nx,
    ny,
    category,
    issued_at,
    forecast_at,
    forecast_at as event_at,
    date_trunc('hour', forecast_at) as time_bucket,
    fcst_value_raw,
    fcst_value_num,
    -- 값 의미 계층(#113): 표현 분류·정량치·범위·코드. fcst_value_num(단일 try_cast)은
    -- 호환용으로 유지 — 신규 소비자는 value_representation + value_num 을 사용할 것.
    {{ kma_value_semantics('category', 'fcst_value_raw') }},
    -- 예보 리드타임(사실값). 원구간(실측 lead>=50h)에서 PCP/SNO 가 bare_numeric
    -- 체제로 전환되는 상관이 관측됨 — 경계 불리언은 공식 문서 검증 전이라 두지 않는다.
    date_diff('hour', issued_at, forecast_at) as forecast_lead_hours,
    raw_object_key,
    payload_hash,
    total_count,
    item_count,
    load_date,
    collected_at,
    dag_run_id
from ranked
where row_num = 1
