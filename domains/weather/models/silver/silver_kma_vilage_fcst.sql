with bronze as (
    select
        cast(request_id as varchar) as request_id,
        cast(source_id as varchar) as source_id,
        cast(request_params_json as varchar) as request_params_json,
        cast(place_id as varchar) as place_id,
        cast(base_date as varchar) as base_date,
        cast(base_time as varchar) as base_time,
        cast(nx as integer) as nx,
        cast(ny as integer) as ny,
        cast(category as varchar) as category,
        cast(fcst_date as varchar) as fcst_date,
        cast(fcst_time as varchar) as fcst_time,
        cast(fcst_value as varchar) as fcst_value_raw,
        try_cast(fcst_value as double) as fcst_value_num,
        cast(raw_object_key as varchar) as raw_object_key,
        cast(payload_hash as varchar) as payload_hash,
        cast(result_code as varchar) as result_code,
        cast(result_msg as varchar) as result_msg,
        cast(total_count as integer) as total_count,
        cast(item_count as integer) as item_count,
        cast(collected_at as timestamp(6)) as collected_at,
        cast(load_date as varchar) as load_date,
        cast(dag_run_id as varchar) as dag_run_id
    from {{ source('weather_bronze', 'kma_vilage_fcst') }}
),

standardized as (
    select
        *,
        {{ kma_timestamp('base_date', 'base_time') }} as issued_at,
        {{ kma_timestamp('fcst_date', 'fcst_time') }} as forecast_at
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
    date_trunc('hour', forecast_at) as time_bucket,
    fcst_value_raw,
    fcst_value_num,
    raw_object_key,
    payload_hash,
    total_count,
    item_count,
    load_date,
    collected_at,
    dag_run_id
from ranked
where row_num = 1
