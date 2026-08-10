{{ config(tags=['traffic_gold_gate']) }}

with flow_keys as (
    select cast(link_id as varchar) as link_id
    from {{ ref('gold_traffic_flow_link_latest') }}
),

context_keys as (
    select cast(link_id as varchar) as link_id
    from {{ ref('gold_traffic_road_congestion_context_current') }}
),

missing_context as (
    select link_id from flow_keys
    except
    select link_id from context_keys
),

unexpected_context as (
    select link_id from context_keys
    except
    select link_id from flow_keys
)

select link_id, 'missing_context' as mismatch_state
from missing_context
union all
select link_id, 'unexpected_context' as mismatch_state
from unexpected_context
