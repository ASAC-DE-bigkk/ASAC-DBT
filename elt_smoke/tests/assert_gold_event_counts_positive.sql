select *
from {{ ref('gold_event_type_metrics') }}
where event_count <= 0
