-- depends_on: {{ ref('silver_seoul_traffic_incident') }}

with latest_run as (
    select dag_run_id
    from {{ source('traffic_bronze', 'seoul_traffic_incident_request_audit') }}
    where dag_run_id is not null
    order by collected_at desc, dag_run_id desc
    limit 1
),

latest_audit as (
    select *
    from {{ source('traffic_bronze', 'seoul_traffic_incident_request_audit') }}
    where dag_run_id = (select dag_run_id from latest_run)
),

coverage as (
    select
        max(dag_run_id) as dag_run_id,
        count(*) as request_count,
        coalesce(sum(row_count), 0) as parsed_row_count,
        coalesce(max(list_total_count), 0) as list_total_count,
        coalesce(max(end_index), 0) as max_end_index
    from latest_audit
)

select
    dag_run_id,
    request_count,
    parsed_row_count,
    list_total_count,
    max_end_index
from coverage
where list_total_count > 0
  and (
      parsed_row_count < list_total_count
      or max_end_index < list_total_count
  )
