{{ config(tags=['traffic_gold_gate']) }}

select
    link_id,
    count(*) as row_count
from {{ ref('gold_traffic_road_congestion_context_current') }}
group by link_id
having link_id is null
    or count(*) > 1
