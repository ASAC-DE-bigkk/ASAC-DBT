with incident_counts as (
    select
        count(*) as incident_row_count,
        count(distinct source_record_id) as incident_incident_count
    from {{ ref('silver_seoul_traffic_incident_current') }}
),

gold_counts as (
    select
        count(*) as gold_row_count,
        count(distinct source_record_id) as gold_incident_count
    from {{ ref('gold_traffic_incident_x_flow') }}
)

select *
from incident_counts
cross join gold_counts
where gold_row_count <> incident_row_count
   or gold_incident_count <> incident_incident_count
