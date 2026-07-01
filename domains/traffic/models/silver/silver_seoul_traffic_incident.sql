with bronze as (
    select
        cast(request_id as varchar) as request_id,
        cast(source_id as varchar) as source_id,
        cast(request_params_json as varchar) as request_params_json,
        cast(start_index as integer) as start_index,
        cast(end_index as integer) as end_index,
        cast(acc_id as varchar) as acc_id,
        cast(occr_date as varchar) as occr_date,
        cast(occr_time as varchar) as occr_time,
        cast(exp_clr_date as varchar) as exp_clr_date,
        cast(exp_clr_time as varchar) as exp_clr_time,
        cast(acc_type as varchar) as acc_type,
        cast(acc_dtype as varchar) as acc_dtype,
        cast(link_id as varchar) as link_id,
        try_cast(grs80tm_x as double) as grs80tm_x,
        try_cast(grs80tm_y as double) as grs80tm_y,
        cast(acc_info as varchar) as acc_info,
        cast(acc_road_code as varchar) as acc_road_code,
        cast(raw_object_key as varchar) as raw_object_key,
        cast(payload_hash as varchar) as payload_hash,
        cast(result_code as varchar) as result_code,
        cast(result_msg as varchar) as result_msg,
        cast(list_total_count as integer) as list_total_count,
        cast(row_count as integer) as row_count,
        cast(collected_at as timestamp(6)) as collected_at,
        cast(load_date as varchar) as load_date,
        cast(dag_run_id as varchar) as dag_run_id
    from {{ source('traffic_bronze', 'seoul_traffic_incident') }}
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
