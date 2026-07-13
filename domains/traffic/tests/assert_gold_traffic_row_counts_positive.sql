-- depends_on: {{ ref('gold_traffic_incident_summary') }}
select 'gold_traffic_incident_summary_empty' as failure_reason
where not exists (
    select 1
    from {{ ref('gold_traffic_incident_summary') }}
)

union all

select concat('negative_counts:', source_id) as failure_reason
from {{ ref('gold_traffic_incident_summary') }}
where row_count < 0
   or raw_object_count < 0
