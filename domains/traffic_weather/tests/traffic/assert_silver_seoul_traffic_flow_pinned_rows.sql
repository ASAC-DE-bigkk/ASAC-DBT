{% set flow_run_id = var('traffic_flow_snapshot_dag_run_id', '') or '' %}
{% set escaped_flow_run_id = flow_run_id | replace("'", "''") %}

select '{{ escaped_flow_run_id }}' as missing_flow_run_id
where '{{ escaped_flow_run_id }}' = ''
   or not exists (
       select 1
       from {{ ref('silver_seoul_traffic_flow') }}
       where cast(dag_run_id as varchar) = '{{ escaped_flow_run_id }}'
   )
