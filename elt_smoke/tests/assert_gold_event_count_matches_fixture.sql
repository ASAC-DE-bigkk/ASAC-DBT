with totals as (
    select coalesce(sum(event_count), 0) as total_event_count
    from {{ ref('gold_event_type_metrics') }}
)

select total_event_count
from totals
where total_event_count <> 5
