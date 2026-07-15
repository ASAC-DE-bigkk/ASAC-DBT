-- Current TOPIS snapshot: the publishable collection run pinned by the transform DAG.
-- The history Silver remains incremental; this table removes incidents that
-- disappeared from the latest complete API snapshot without losing Bronze history.
-- depends_on: {{ ref('silver_seoul_traffic_incident') }}

{{ config(materialized='table') }}

{% set snapshot_dag_run_id = var('traffic_snapshot_dag_run_id') %}

with latest_manifest_state as (
    {{ latest_manifest_run_state('traffic_bronze', 'collection_run_manifest', 'seoul_traffic_incident') }}
),

pinned_run as (
    select dag_run_id
    from latest_manifest_state
    where manifest_status = 'SUCCESS'
      and is_publishable
      and dag_run_id = '{{ snapshot_dag_run_id | replace("'", "''") }}'
)

select history.*
from {{ ref('silver_seoul_traffic_incident') }} as history
inner join pinned_run
    on history.dag_run_id = pinned_run.dag_run_id
