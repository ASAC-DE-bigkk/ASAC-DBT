-- gold: source-level traffic incident summary.
--
-- Keep this model as table materialization for now. It aggregates the current
-- complete snapshot into one row per source_id, so rebuilding the tiny summary
-- avoids stale counts without re-scanning Bronze history.

with latest_source as (
    select source_id
    from {{ source('traffic_bronze', 'collection_run_manifest') }}
    where source_id = 'seoul_traffic_incident'
      and status = 'SUCCESS'
      and is_publishable
    order by cast(event_at as timestamp(6)) desc, cast(dag_run_id as varchar) desc
    limit 1
),

current_counts as (
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
    from {{ ref('silver_seoul_traffic_incident_current') }}
    group by source_id
)

select
    latest_source.source_id,
    coalesce(current_counts.row_count, 0) as row_count,
    coalesce(current_counts.raw_object_count, 0) as raw_object_count,
    coalesce(current_counts.source_coordinate_row_count, 0) as source_coordinate_row_count,
    coalesce(current_counts.missing_source_coordinate_row_count, 0)
        as missing_source_coordinate_row_count,
    current_counts.first_occurred_at,
    current_counts.last_occurred_at,
    current_counts.last_collected_at
from latest_source
left join current_counts
    on latest_source.source_id = current_counts.source_id
