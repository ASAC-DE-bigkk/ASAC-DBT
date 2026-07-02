with publishable_runs as (
    select distinct cast(dag_run_id as varchar) as dag_run_id
    from {{ source('traffic_bronze', 'collection_run_manifest') }}
    where source_id = 'seoul_traffic_incident'
      and status = 'SUCCESS'
      and is_publishable
),

bronze as (
    select
        cast(bronze.request_id as varchar) as request_id,
        cast(bronze.source_id as varchar) as source_id,
        cast(bronze.request_params_json as varchar) as request_params_json,
        cast(bronze.start_index as integer) as start_index,
        cast(bronze.end_index as integer) as end_index,
        cast(bronze.acc_id as varchar) as acc_id,
        cast(bronze.occr_date as varchar) as occr_date,
        cast(bronze.occr_time as varchar) as occr_time,
        cast(bronze.exp_clr_date as varchar) as exp_clr_date,
        cast(bronze.exp_clr_time as varchar) as exp_clr_time,
        cast(bronze.acc_type as varchar) as acc_type,
        cast(bronze.acc_dtype as varchar) as acc_dtype,
        cast(bronze.link_id as varchar) as link_id,
        try_cast(bronze.grs80tm_x as double) as grs80tm_x,
        try_cast(bronze.grs80tm_y as double) as grs80tm_y,
        cast(bronze.acc_info as varchar) as acc_info,
        cast(bronze.acc_road_code as varchar) as acc_road_code,
        cast(bronze.raw_object_key as varchar) as raw_object_key,
        cast(bronze.payload_hash as varchar) as payload_hash,
        cast(bronze.result_code as varchar) as result_code,
        cast(bronze.result_msg as varchar) as result_msg,
        cast(bronze.list_total_count as integer) as list_total_count,
        cast(bronze.row_count as integer) as row_count,
        cast(bronze.collected_at as timestamp(6)) as collected_at,
        cast(bronze.load_date as varchar) as load_date,
        cast(bronze.dag_run_id as varchar) as dag_run_id
    from {{ source('traffic_bronze', 'seoul_traffic_incident') }} as bronze
    inner join publishable_runs
        on cast(bronze.dag_run_id as varchar) = publishable_runs.dag_run_id
),

standardized as (
    select
        *,
        {{ topis_timestamp('occr_date', 'occr_time') }} as occurred_at,
        {{ topis_timestamp('exp_clr_date', 'exp_clr_time') }} as expected_clear_at,
        'GRS80_TM' as source_coordinate_system,
        case
            when grs80tm_x is not null and grs80tm_y is not null
                then 'source_coordinate_available'
            else 'source_coordinate_missing'
        end as source_location_quality
    from bronze
    where result_code = 'INFO-000'
),

ranked as (
    select
        *,
        row_number() over (
            partition by acc_id
            order by collected_at desc, raw_object_key desc, request_id desc
        ) as row_num
    from standardized
    where acc_id is not null
      and occurred_at is not null
)

select
    request_id,
    source_id,
    request_params_json,
    acc_id as source_record_id,
    acc_type,
    acc_dtype,
    link_id as asset_id,
    acc_road_code,
    acc_info,
    source_coordinate_system,
    source_location_quality,
    grs80tm_x,
    grs80tm_y,
    occurred_at,
    expected_clear_at,
    occurred_at as valid_from,
    expected_clear_at as valid_to,
    date_trunc('hour', occurred_at) as time_bucket,
    raw_object_key,
    payload_hash,
    list_total_count,
    row_count,
    load_date,
    collected_at,
    dag_run_id
from ranked
where row_num = 1
