select
    source_id,
    count(*) as row_count,
    count(distinct raw_object_key) as raw_object_count,
    min(occurred_at) as first_occurred_at,
    max(occurred_at) as last_occurred_at,
    max(collected_at) as last_collected_at
from {{ ref('silver_seoul_traffic_incident') }}
group by source_id
