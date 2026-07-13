-- depends_on: {{ ref('silver_seoul_traffic_incident') }}
select
    source_record_id,
    count(*) as row_count
from {{ ref('silver_seoul_traffic_incident') }}
group by source_record_id
having count(*) > 1
