-- gold: source-level traffic incident summary.
--
-- Keep this model as table materialization for now. It aggregates the full
-- incremental silver table into one row per source_id, so rebuilding the tiny
-- summary avoids stale counts without re-scanning bronze.

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
from {{ ref('silver_seoul_traffic_incident') }}
group by source_id
