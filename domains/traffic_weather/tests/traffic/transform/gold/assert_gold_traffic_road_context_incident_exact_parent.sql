{{ config(tags=['traffic_gold_gate']) }}

with expected as (
    select
        context.product_row_id,
        count(incident.source_record_id) as expected_incident_count
    from {{ ref('gold_traffic_road_congestion_context_current') }} as context
    left join {{ ref('silver_seoul_traffic_incident_current') }} as incident
        on cast(incident.asset_id as varchar) = context.link_id
       and cast(incident.dag_run_id as varchar) = context.parent_incident_run_id
    group by context.product_row_id
)

select
    context.product_row_id,
    context.link_id,
    context.parent_incident_run_id,
    context.incident_context_state,
    context.incident_count,
    expected.expected_incident_count
from {{ ref('gold_traffic_road_congestion_context_current') }} as context
inner join expected
    on context.product_row_id = expected.product_row_id
where (
        context.incident_context_state = 'matched_exact_parent'
        and (
            expected.expected_incident_count = 0
            or context.incident_count <> expected.expected_incident_count
        )
    )
   or (
        context.incident_context_state <> 'matched_exact_parent'
        and expected.expected_incident_count > 0
    )
