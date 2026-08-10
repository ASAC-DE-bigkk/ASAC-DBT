select
    link_id,
    count(*) as row_count
from {{ ref('silver_seoul_traffic_link_reference') }}
group by link_id
having count(*) <> 1
