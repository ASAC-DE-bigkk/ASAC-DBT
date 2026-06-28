with bronze as (
    select
        cast(request_id as varchar) as request_id,
        cast(source_id as varchar) as source_id,
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
        cast(dag_run_id as varchar) as dag_run_id
    from {{ source('ask_seoul_bronze', 'seoul_traffic_incident') }}
),

normalized_time as (
    select
        *,
        case
            when regexp_like(occr_time, '^[0-9]{4}$') then concat(occr_time, '00')
            when regexp_like(occr_time, '^[0-9]{6}$') then occr_time
        end as occr_time_hhmmss,
        case
            when regexp_like(exp_clr_time, '^[0-9]{4}$') then concat(exp_clr_time, '00')
            when regexp_like(exp_clr_time, '^[0-9]{6}$') then exp_clr_time
        end as exp_clr_time_hhmmss
    from bronze
    where result_code = 'INFO-000'
),

standardized as (
    select
        *,
        case
            when regexp_like(occr_date, '^[0-9]{8}$') and occr_time_hhmmss is not null
                then cast(date_parse(concat(occr_date, occr_time_hhmmss), '%Y%m%d%H%i%s') as timestamp(6))
        end as occurred_at,
        case
            when regexp_like(exp_clr_date, '^[0-9]{8}$') and exp_clr_time_hhmmss is not null
                then cast(date_parse(concat(exp_clr_date, exp_clr_time_hhmmss), '%Y%m%d%H%i%s') as timestamp(6))
        end as expected_clear_at
    from normalized_time
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
)

select
    request_id,
    source_id,
    acc_id as source_record_id,
    acc_type,
    acc_dtype,
    link_id as asset_id,
    acc_road_code,
    acc_info,
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
    collected_at,
    dag_run_id
from ranked
where row_num = 1
