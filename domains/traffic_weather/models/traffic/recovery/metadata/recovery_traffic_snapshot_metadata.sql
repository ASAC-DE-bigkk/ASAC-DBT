-- Completed recovery anchor read from the Silver table's atomic marker row.
-- It cannot advance to a later requested snapshot unless that Silver CTAS succeeds.

{{ config(
    materialized='table',
    views_enabled=false,
    on_table_exists='drop',
) }}

select
    cast(source_id as varchar) as source_id,
    cast(dag_run_id as varchar) as snapshot_dag_run_id
from {{ ref('recovery_silver_seoul_traffic_incident') }}
where is_snapshot_marker
