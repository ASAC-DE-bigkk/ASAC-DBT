-- Latest complete TOPIS LinkInfo row per road link.

with attempts as (
    {{ traffic_link_reference_attempts() }}
),

complete_ranked as (
    select
        *,
        row_number() over (
            partition by link_id
            order by attempt_collected_at desc, dag_run_id desc
        ) as complete_row_num
    from attempts
    where is_complete
),

winner as (
    select *
    from complete_ranked
    where complete_row_num = 1
)

select
    cast(info.request_id as varchar) as request_id,
    cast(info.source_id as varchar) as source_id,
    cast(info.service_name as varchar) as service_name,
    cast(info.request_params_json as varchar) as request_params_json,
    cast(info.link_id as varchar) as link_id,
    nullif(trim(cast(info.road_name as varchar)), '') as road_name,
    nullif(trim(cast(info.start_node_name as varchar)), '') as start_node_name,
    nullif(trim(cast(info.end_node_name as varchar)), '') as end_node_name,
    try_cast(info.map_distance as double) as map_distance,
    nullif(trim(cast(info.region_code as varchar)), '') as region_code,
    cast(info.raw_object_key as varchar) as raw_object_key,
    cast(info.payload_hash as varchar) as payload_hash,
    try_cast(info.http_status as integer) as http_status,
    cast(info.result_code as varchar) as result_code,
    cast(info.result_msg as varchar) as result_msg,
    try_cast(info.list_total_count as bigint) as list_total_count,
    try_cast(info.row_count as bigint) as row_count,
    cast(info.collected_at as timestamp(6)) as collected_at,
    cast(winner.attempt_collected_at as timestamp(6)) as reference_collected_at,
    cast(info.load_date as varchar) as load_date,
    cast(info.dag_run_id as varchar) as dag_run_id
from {{ source('traffic_bronze', 'seoul_traffic_link_info') }} as info
inner join winner
    on cast(info.link_id as varchar) = winner.link_id
   and cast(info.dag_run_id as varchar) = winner.dag_run_id
where lower(cast(info.service_name as varchar)) = 'linkinfo'
  and cast(info.result_code as varchar) = 'INFO-000'
