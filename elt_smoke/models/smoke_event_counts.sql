select
    event_type,
    count(*) as event_count,
    min(event_ts) as first_event_ts,
    max(event_ts) as last_event_ts
from {{ ref('sample_events') }}
group by event_type
