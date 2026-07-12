-- Current TOPIS snapshot: only the latest complete, publishable collection run.
-- The history Silver remains incremental; this table removes incidents that
-- disappeared from the latest complete API snapshot without losing Bronze history.

{{ config(materialized='table') }}

with latest_run as (
    select cast(dag_run_id as varchar) as dag_run_id
    from {{ source('traffic_bronze', 'collection_run_manifest') }}
    where source_id = 'seoul_traffic_incident'
      and status = 'SUCCESS'
      and is_publishable
    order by cast(event_at as timestamp(6)) desc, cast(dag_run_id as varchar) desc
    limit 1
)

select history.*
from {{ ref('silver_seoul_traffic_incident') }} as history
inner join latest_run
    on history.dag_run_id = latest_run.dag_run_id
