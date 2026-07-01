with latest_audit as (
    select *
    from {{ source('traffic_bronze', 'seoul_traffic_incident_request_audit') }}
    where collected_at = (
        select max(collected_at)
        from {{ source('traffic_bronze', 'seoul_traffic_incident_request_audit') }}
    )
),

coverage as (
    select
        coalesce(sum(row_count), 0) as parsed_row_count,
        coalesce(max(list_total_count), 0) as list_total_count,
        coalesce(max(end_index), 0) as max_end_index
    from latest_audit
)

select
    parsed_row_count,
    list_total_count,
    max_end_index
from coverage
where list_total_count > 0
  and parsed_row_count < list_total_count
  and max_end_index < list_total_count
