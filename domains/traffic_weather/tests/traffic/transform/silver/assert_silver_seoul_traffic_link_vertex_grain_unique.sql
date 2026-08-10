select
    link_id,
    vertex_sequence,
    count(*) as row_count
from {{ ref('silver_seoul_traffic_link_vertex') }}
group by link_id, vertex_sequence
having count(*) <> 1
