-- Current TOPIS snapshot: the publishable collection run pinned by the transform DAG.
-- The history Silver remains incremental; this table removes incidents that
-- disappeared from the latest complete API snapshot without losing Bronze history.
-- depends_on: {{ ref('silver_seoul_traffic_incident') }}

{{ config(materialized='table') }}

{% set snapshot_dag_run_id = var('traffic_snapshot_dag_run_id') %}

with pinned_run as (
    select cast(dag_run_id as varchar) as dag_run_id
    from {{ source('traffic_bronze', 'collection_run_manifest') }}
    where source_id = 'seoul_traffic_incident'
      and status = 'SUCCESS'
      and is_publishable
      and cast(dag_run_id as varchar) = '{{ snapshot_dag_run_id | replace("'", "''") }}'
)

select history.*
from {{ ref('silver_seoul_traffic_incident') }} as history
inner join pinned_run
    on history.dag_run_id = pinned_run.dag_run_id
