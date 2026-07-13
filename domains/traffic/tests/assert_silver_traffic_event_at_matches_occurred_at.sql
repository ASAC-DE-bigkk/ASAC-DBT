-- depends_on: {{ ref('silver_seoul_traffic_incident') }}
select *
from {{ ref('silver_seoul_traffic_incident') }}
where event_at is null
   or event_at <> occurred_at
