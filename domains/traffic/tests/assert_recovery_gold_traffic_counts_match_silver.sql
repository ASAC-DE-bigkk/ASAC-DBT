{% set snapshot_dag_run_id = var('traffic_snapshot_dag_run_id') %}

with requested_run as (
    select '{{ snapshot_dag_run_id | replace("'", "''") }}' as snapshot_dag_run_id
),

configured_run as (
    select distinct
        'seoul_traffic_incident' as source_id,
        cast(manifest.dag_run_id as varchar) as snapshot_dag_run_id
    from {{ source('traffic_bronze', 'collection_run_manifest') }} as manifest
    inner join requested_run
        on cast(manifest.dag_run_id as varchar) = requested_run.snapshot_dag_run_id
    where manifest.source_id = 'seoul_traffic_incident'
      and manifest.status = 'SUCCESS'
      and manifest.is_publishable
),

metadata_run as (
    select
        cast(source_id as varchar) as source_id,
        cast(snapshot_dag_run_id as varchar) as snapshot_dag_run_id
    from {{ target.database }}.{{ target.schema }}.recovery_traffic_snapshot_metadata
),

silver_marker_run as (
    select
        cast(source_id as varchar) as source_id,
        cast(dag_run_id as varchar) as snapshot_dag_run_id
    from {{ target.database }}.{{ target.schema }}.recovery_silver_seoul_traffic_incident
    where is_snapshot_marker
),

missing_pinned_run as (
    select
        'missing_pinned_run' as violation_type,
        requested_run.snapshot_dag_run_id as source_id,
        cast(null as varchar) as snapshot_dag_run_id,
        cast(null as bigint) as silver_row_count,
        cast(null as bigint) as gold_row_count,
        cast(null as bigint) as silver_raw_object_count,
        cast(null as bigint) as gold_raw_object_count,
        cast(null as bigint) as silver_source_coordinate_row_count,
        cast(null as bigint) as gold_source_coordinate_row_count,
        cast(null as bigint) as silver_missing_source_coordinate_row_count,
        cast(null as bigint) as gold_missing_source_coordinate_row_count,
        cast(null as timestamp(6)) as silver_first_occurred_at,
        cast(null as timestamp(6)) as gold_first_occurred_at,
        cast(null as timestamp(6)) as silver_last_occurred_at,
        cast(null as timestamp(6)) as gold_last_occurred_at,
        cast(null as timestamp(6)) as silver_last_collected_at,
        cast(null as timestamp(6)) as gold_last_collected_at
    from requested_run
    left join configured_run
        on requested_run.snapshot_dag_run_id = configured_run.snapshot_dag_run_id
    where configured_run.snapshot_dag_run_id is null
),

metadata_run_mismatch as (
    select
        'metadata_run_mismatch' as violation_type,
        coalesce(configured_run.source_id, metadata_run.source_id) as source_id,
        coalesce(configured_run.snapshot_dag_run_id, metadata_run.snapshot_dag_run_id)
            as snapshot_dag_run_id,
        cast(null as bigint) as silver_row_count,
        cast(null as bigint) as gold_row_count,
        cast(null as bigint) as silver_raw_object_count,
        cast(null as bigint) as gold_raw_object_count,
        cast(null as bigint) as silver_source_coordinate_row_count,
        cast(null as bigint) as gold_source_coordinate_row_count,
        cast(null as bigint) as silver_missing_source_coordinate_row_count,
        cast(null as bigint) as gold_missing_source_coordinate_row_count,
        cast(null as timestamp(6)) as silver_first_occurred_at,
        cast(null as timestamp(6)) as gold_first_occurred_at,
        cast(null as timestamp(6)) as silver_last_occurred_at,
        cast(null as timestamp(6)) as gold_last_occurred_at,
        cast(null as timestamp(6)) as silver_last_collected_at,
        cast(null as timestamp(6)) as gold_last_collected_at
    from configured_run
    full outer join metadata_run
        on configured_run.source_id = metadata_run.source_id
       and configured_run.snapshot_dag_run_id = metadata_run.snapshot_dag_run_id
    where exists (select 1 from configured_run)
      and (
          configured_run.source_id is null
          or metadata_run.source_id is null
          or configured_run.snapshot_dag_run_id is distinct from metadata_run.snapshot_dag_run_id
      )
),

silver_marker_run_mismatch as (
    select
        'silver_marker_run_mismatch' as violation_type,
        coalesce(metadata_run.source_id, silver_marker_run.source_id) as source_id,
        coalesce(metadata_run.snapshot_dag_run_id, silver_marker_run.snapshot_dag_run_id)
            as snapshot_dag_run_id,
        cast(null as bigint) as silver_row_count,
        cast(null as bigint) as gold_row_count,
        cast(null as bigint) as silver_raw_object_count,
        cast(null as bigint) as gold_raw_object_count,
        cast(null as bigint) as silver_source_coordinate_row_count,
        cast(null as bigint) as gold_source_coordinate_row_count,
        cast(null as bigint) as silver_missing_source_coordinate_row_count,
        cast(null as bigint) as gold_missing_source_coordinate_row_count,
        cast(null as timestamp(6)) as silver_first_occurred_at,
        cast(null as timestamp(6)) as gold_first_occurred_at,
        cast(null as timestamp(6)) as silver_last_occurred_at,
        cast(null as timestamp(6)) as gold_last_occurred_at,
        cast(null as timestamp(6)) as silver_last_collected_at,
        cast(null as timestamp(6)) as gold_last_collected_at
    from metadata_run
    full outer join silver_marker_run
        on metadata_run.source_id = silver_marker_run.source_id
       and metadata_run.snapshot_dag_run_id = silver_marker_run.snapshot_dag_run_id
    where exists (select 1 from configured_run)
      and (
          metadata_run.source_id is null
          or silver_marker_run.source_id is null
          or metadata_run.snapshot_dag_run_id is distinct from silver_marker_run.snapshot_dag_run_id
      )
),

silver_counts as (
    select
        source_id,
        cast(dag_run_id as varchar) as snapshot_dag_run_id,
        count(*) as row_count,
        count(distinct raw_object_key) as raw_object_count,
        sum(case when source_location_quality = 'source_coordinate_available' then 1 else 0 end)
            as source_coordinate_row_count,
        sum(case when source_location_quality = 'source_coordinate_missing' then 1 else 0 end)
            as missing_source_coordinate_row_count,
        min(occurred_at) as first_occurred_at,
        max(occurred_at) as last_occurred_at,
        max(collected_at) as last_collected_at
    from {{ target.database }}.{{ target.schema }}.recovery_silver_seoul_traffic_incident
    where not is_snapshot_marker
    group by source_id, cast(dag_run_id as varchar)
),

expected_gold as (
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
        on configured_run.source_id = silver_counts.source_id
       and configured_run.snapshot_dag_run_id = silver_counts.snapshot_dag_run_id
),

actual_gold as (
    select
        cast(source_id as varchar) as source_id,
        cast(snapshot_dag_run_id as varchar) as snapshot_dag_run_id,
        row_count,
        raw_object_count,
        source_coordinate_row_count,
        missing_source_coordinate_row_count,
        first_occurred_at,
        last_occurred_at,
        last_collected_at
    from {{ target.database }}.{{ target.schema }}.recovery_gold_traffic_incident_summary
),

gold_mismatch as (
    select
        'recovery_gold_mismatch' as violation_type,
        coalesce(s.source_id, g.source_id) as source_id,
        coalesce(s.snapshot_dag_run_id, g.snapshot_dag_run_id) as snapshot_dag_run_id,
        s.row_count as silver_row_count,
        g.row_count as gold_row_count,
        s.raw_object_count as silver_raw_object_count,
        g.raw_object_count as gold_raw_object_count,
        s.source_coordinate_row_count as silver_source_coordinate_row_count,
        g.source_coordinate_row_count as gold_source_coordinate_row_count,
        s.missing_source_coordinate_row_count as silver_missing_source_coordinate_row_count,
        g.missing_source_coordinate_row_count as gold_missing_source_coordinate_row_count,
        s.first_occurred_at as silver_first_occurred_at,
        g.first_occurred_at as gold_first_occurred_at,
        s.last_occurred_at as silver_last_occurred_at,
        g.last_occurred_at as gold_last_occurred_at,
        s.last_collected_at as silver_last_collected_at,
        g.last_collected_at as gold_last_collected_at
    from expected_gold as s
    full outer join actual_gold as g
        on s.source_id = g.source_id
       and s.snapshot_dag_run_id = g.snapshot_dag_run_id
    where exists (select 1 from configured_run)
      and not exists (select 1 from metadata_run_mismatch)
      and not exists (select 1 from silver_marker_run_mismatch)
      and (
          s.source_id is null
          or g.source_id is null
          or s.snapshot_dag_run_id is distinct from g.snapshot_dag_run_id
          or s.row_count is distinct from g.row_count
          or s.raw_object_count is distinct from g.raw_object_count
          or s.source_coordinate_row_count is distinct from g.source_coordinate_row_count
          or s.missing_source_coordinate_row_count is distinct from g.missing_source_coordinate_row_count
          or s.first_occurred_at is distinct from g.first_occurred_at
          or s.last_occurred_at is distinct from g.last_occurred_at
          or s.last_collected_at is distinct from g.last_collected_at
      )
)

select * from missing_pinned_run
union all
select * from metadata_run_mismatch
union all
select * from silver_marker_run_mismatch
union all
select * from gold_mismatch
