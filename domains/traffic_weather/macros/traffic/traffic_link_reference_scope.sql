{% macro traffic_link_reference_attempts() %}
with audit as (
    select
        cast(link_id as varchar) as link_id,
        cast(dag_run_id as varchar) as dag_run_id,
        max(cast(collected_at as timestamp(6))) as attempt_collected_at,
        count_if(
            lower(cast(service_name as varchar)) = 'linkinfo'
            and cast(result_code as varchar) = 'INFO-000'
        ) as info_success_count,
        count_if(
            lower(cast(service_name as varchar)) = 'linkverinfo'
            and cast(result_code as varchar) = 'INFO-000'
        ) as vertex_success_count,
        max(
            case when lower(cast(service_name as varchar)) = 'linkinfo'
                then try_cast(row_count as bigint) end
        ) as info_audit_row_count,
        max(
            case when lower(cast(service_name as varchar)) = 'linkinfo'
                then try_cast(list_total_count as bigint) end
        ) as info_audit_total_count,
        max(
            case when lower(cast(service_name as varchar)) = 'linkverinfo'
                then try_cast(row_count as bigint) end
        ) as vertex_audit_row_count,
        max(
            case when lower(cast(service_name as varchar)) = 'linkverinfo'
                then try_cast(list_total_count as bigint) end
        ) as vertex_audit_total_count
    from {{ source('traffic_bronze', 'seoul_traffic_link_request_audit') }}
    group by link_id, dag_run_id
),
info_actual as (
    select
        cast(link_id as varchar) as link_id,
        cast(dag_run_id as varchar) as dag_run_id,
        count(*) as info_actual_count
    from {{ source('traffic_bronze', 'seoul_traffic_link_info') }}
    group by link_id, dag_run_id
),
vertex_actual as (
    select
        cast(link_id as varchar) as link_id,
        cast(dag_run_id as varchar) as dag_run_id,
        count(*) as vertex_actual_count,
        count(distinct try_cast(vertex_sequence as integer))
            as vertex_sequence_distinct_count
    from {{ source('traffic_bronze', 'seoul_traffic_link_vertex') }}
    group by link_id, dag_run_id
)
select
    audit.link_id,
    audit.dag_run_id,
    audit.attempt_collected_at,
    audit.info_success_count,
    audit.vertex_success_count,
    audit.info_audit_row_count,
    audit.info_audit_total_count,
    audit.vertex_audit_row_count,
    audit.vertex_audit_total_count,
    coalesce(info_actual.info_actual_count, 0) as info_actual_count,
    coalesce(vertex_actual.vertex_actual_count, 0) as vertex_actual_count,
    coalesce(vertex_actual.vertex_sequence_distinct_count, 0)
        as vertex_sequence_distinct_count,
    case
        when info_success_count = 1
         and vertex_success_count = 1
         and info_audit_row_count = 1
         and info_audit_total_count = 1
         and info_actual_count = 1
         and vertex_audit_row_count >= 1
         and vertex_audit_row_count = vertex_audit_total_count
         and vertex_actual_count = vertex_audit_row_count
         and vertex_sequence_distinct_count = vertex_actual_count
        then true else false
    end as is_complete
from audit
left join info_actual
  on audit.link_id = info_actual.link_id
 and audit.dag_run_id = info_actual.dag_run_id
left join vertex_actual
  on audit.link_id = vertex_actual.link_id
 and audit.dag_run_id = vertex_actual.dag_run_id
{% endmacro %}
