-- Recovery-only Gold summary derived only from the requested recovery Silver table.

{{ config(
    materialized='table',
    views_enabled=false,
    on_table_exists='drop',
    tags=['traffic_snapshot_recovery', 'traffic_snapshot_recovery_gold'],
) }}

with completed_metadata as (
    select
        cast(source_id as varchar) as source_id,
        cast(snapshot_dag_run_id as varchar) as snapshot_dag_run_id
    from {{ ref('recovery_traffic_snapshot_metadata') }}
),

silver_marker as (
    select
        cast(source_id as varchar) as source_id,
        cast(dag_run_id as varchar) as snapshot_dag_run_id
    from {{ ref('recovery_silver_seoul_traffic_incident') }}
    where is_snapshot_marker
),

configured_run as (
    select completed_metadata.source_id, completed_metadata.snapshot_dag_run_id
    from completed_metadata
    inner join silver_marker
        on completed_metadata.source_id = silver_marker.source_id
       and completed_metadata.snapshot_dag_run_id = silver_marker.snapshot_dag_run_id
),

silver_counts as (
    select
        source_id,
        count(*) as row_count,
        count(distinct raw_object_key) as raw_object_count,
        sum(case when source_location_quality = 'source_coordinate_available' then 1 else 0 end)
            as source_coordinate_row_count,
        sum(case when source_location_quality = 'source_coordinate_missing' then 1 else 0 end)
            as missing_source_coordinate_row_count,
        min(occurred_at) as first_occurred_at,
        max(occurred_at) as last_occurred_at,
        max(collected_at) as last_collected_at
    from {{ ref('recovery_silver_seoul_traffic_incident') }}
    where not is_snapshot_marker
    group by source_id
)

select
    configured_run.source_id,
    configured_run.snapshot_dag_run_id,
    coalesce(silver_counts.row_count, 0) as row_count,
    coalesce(silver_counts.raw_object_count, 0) as raw_object_count,
    coalesce(silver_counts.source_coordinate_row_count, 0) as source_coordinate_row_count,
    coalesce(silver_counts.missing_source_coordinate_row_count, 0)
        as missing_source_coordinate_row_count,
    silver_counts.first_occurred_at,
    silver_counts.last_occurred_at,
    silver_counts.last_collected_at
from configured_run
left join silver_counts
    on silver_counts.source_id = configured_run.source_id
