{% macro traffic_incident_snapshot_dag_run_id_sql_literal() -%}
  {%- set snapshot_dag_run_id = var('traffic_snapshot_dag_run_id', '') or '' -%}
  '{{ snapshot_dag_run_id | replace("'", "''") }}'
{%- endmacro %}

{% macro traffic_incident_snapshot_horizon() -%}
select max(cast(event_at as timestamp(6))) as snapshot_horizon_at_utc
from {{ source('traffic_bronze', 'collection_run_manifest') }}
where cast(source_id as varchar) = 'seoul_traffic_incident'
  and cast(dag_run_id as varchar)
      = {{ traffic_incident_snapshot_dag_run_id_sql_literal() }}
  and cast(status as varchar) = 'SUCCESS'
  and coalesce(cast(is_publishable as boolean), false)
{%- endmacro %}

{% macro traffic_incident_manifest_run_state_at_snapshot() -%}
select
    source_id,
    dag_run_id,
    collection_dag_id,
    manifest_status,
    is_publishable,
    manifest_failure_reason,
    manifest_event_at_utc,
    manifest_state_tie_count
from (
    select
        cast(manifest.source_id as varchar) as source_id,
        cast(manifest.dag_run_id as varchar) as dag_run_id,
        cast(manifest.dag_id as varchar) as collection_dag_id,
        cast(manifest.status as varchar) as manifest_status,
        cast(manifest.is_publishable as boolean) as is_publishable,
        cast(manifest.failure_reason as varchar) as manifest_failure_reason,
        cast(manifest.event_at as timestamp(6)) as manifest_event_at_utc,
        count(*) over (
            partition by
                cast(manifest.source_id as varchar),
                cast(manifest.dag_run_id as varchar),
                cast(manifest.event_at as timestamp(6)),
                cast(manifest.dag_id as varchar)
        ) as manifest_state_tie_count,
        row_number() over (
            partition by
                cast(manifest.source_id as varchar),
                cast(manifest.dag_run_id as varchar)
            order by
                cast(manifest.event_at as timestamp(6)) desc,
                cast(manifest.dag_id as varchar) desc
        ) as manifest_row_num
    from {{ source('traffic_bronze', 'collection_run_manifest') }} as manifest
    cross join pinned_manifest_horizon as horizon
    where cast(manifest.source_id as varchar) = 'seoul_traffic_incident'
      and cast(manifest.event_at as timestamp(6))
          <= horizon.snapshot_horizon_at_utc
) as manifest_state
where manifest_row_num = 1
  and manifest_state_tie_count = 1
{%- endmacro %}

{% macro traffic_incident_manifest_run_history() -%}
select distinct cast(dag_run_id as varchar) as dag_run_id
from {{ source('traffic_bronze', 'collection_run_manifest') }}
where cast(source_id as varchar) = 'seoul_traffic_incident'
{%- endmacro %}
