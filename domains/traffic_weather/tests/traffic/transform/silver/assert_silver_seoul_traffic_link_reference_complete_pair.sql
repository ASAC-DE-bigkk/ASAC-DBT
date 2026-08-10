with attempts as (
    {{ traffic_link_reference_attempts() }}
),

info as (
    select link_id, dag_run_id
    from {{ ref('silver_seoul_traffic_link_info') }}
),

vertices as (
    select
        link_id,
        dag_run_id,
        count(*) as silver_vertex_count
    from {{ ref('silver_seoul_traffic_link_vertex') }}
    group by link_id, dag_run_id
),

selected as (
    select
        coalesce(info.link_id, vertices.link_id) as link_id,
        coalesce(info.dag_run_id, vertices.dag_run_id) as dag_run_id,
        info.link_id as info_link_id,
        vertices.link_id as vertex_link_id,
        vertices.silver_vertex_count,
        attempts.is_complete,
        attempts.vertex_actual_count,
        attempts.vertex_audit_row_count
    from info
    full outer join vertices
      on info.link_id = vertices.link_id
     and info.dag_run_id = vertices.dag_run_id
    left join attempts
      on coalesce(info.link_id, vertices.link_id) = attempts.link_id
     and coalesce(info.dag_run_id, vertices.dag_run_id) = attempts.dag_run_id
)

select *
from selected
where info_link_id is null
   or vertex_link_id is null
   or is_complete is not true
   or vertex_actual_count <> vertex_audit_row_count
   or silver_vertex_count <> vertex_audit_row_count
