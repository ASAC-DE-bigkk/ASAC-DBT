-- Ordered TOPIS LinkVerInfo vertices from the latest complete run per road link.

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
    cast(vertex.request_id as varchar) as request_id,
    cast(vertex.source_id as varchar) as source_id,
    cast(vertex.service_name as varchar) as service_name,
    cast(vertex.request_params_json as varchar) as request_params_json,
    cast(vertex.link_id as varchar) as link_id,
    try_cast(vertex.vertex_sequence as integer) as vertex_sequence,
    try_cast(vertex.grs80tm_x as double) as grs80tm_x,
    try_cast(vertex.grs80tm_y as double) as grs80tm_y,
    cast(vertex.raw_object_key as varchar) as raw_object_key,
    cast(vertex.payload_hash as varchar) as payload_hash,
    try_cast(vertex.http_status as integer) as http_status,
    cast(vertex.result_code as varchar) as result_code,
    cast(vertex.result_msg as varchar) as result_msg,
    try_cast(vertex.list_total_count as bigint) as list_total_count,
    try_cast(vertex.row_count as bigint) as row_count,
    cast(vertex.collected_at as timestamp(6)) as collected_at,
    cast(winner.attempt_collected_at as timestamp(6)) as reference_collected_at,
    cast(vertex.load_date as varchar) as load_date,
    cast(vertex.dag_run_id as varchar) as dag_run_id
from {{ source('traffic_bronze', 'seoul_traffic_link_vertex') }} as vertex
inner join winner
    on cast(vertex.link_id as varchar) = winner.link_id
   and cast(vertex.dag_run_id as varchar) = winner.dag_run_id
where lower(cast(vertex.service_name as varchar)) = 'linkverinfo'
  and cast(vertex.result_code as varchar) = 'INFO-000'
  and try_cast(vertex.vertex_sequence as integer) is not null
  and try_cast(vertex.grs80tm_x as double) is not null
  and try_cast(vertex.grs80tm_y as double) is not null
