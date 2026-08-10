{{ config(tags=['traffic_gold_gate']) }}

select
    product_row_id,
    link_id,
    incident_context_state,
    weather_context_state,
    incident_count,
    weather_category_coverage_count
from {{ ref('gold_traffic_road_congestion_context_current') }}
where incident_context_state not in (
        'missing_parent_lineage',
        'matched_exact_parent',
        'no_incident_in_exact_parent',
        'parent_snapshot_not_current'
    )
   or weather_context_state not in (
        'missing_link_location',
        'missing_weather_bridge',
        'missing_weather_context',
        'partial_weather_context',
        'available'
    )
   or (
        incident_context_state = 'missing_parent_lineage'
        and parent_incident_run_id is not null
        and trim(parent_incident_run_id) <> ''
    )
   or (
        incident_context_state <> 'missing_parent_lineage'
        and (parent_incident_run_id is null or trim(parent_incident_run_id) = '')
    )
   or (
        incident_context_state = 'matched_exact_parent'
        and (incident_count <= 0 or latest_incident_occurred_at_kst is null)
    )
   or (
        incident_context_state <> 'matched_exact_parent'
        and incident_count <> 0
    )
   or weather_category_coverage_count < 0
   or weather_category_coverage_count > 6
   or (
        weather_context_state in (
            'missing_link_location',
            'missing_weather_bridge',
            'missing_weather_context'
        )
        and weather_category_coverage_count <> 0
    )
   or (
        weather_context_state = 'missing_link_location'
        and admin_dong_code is not null
    )
   or (
        weather_context_state <> 'missing_link_location'
        and admin_dong_code is null
    )
   or (
        weather_context_state = 'partial_weather_context'
        and weather_category_coverage_count not between 1 and 5
    )
   or (
        weather_context_state = 'available'
        and weather_category_coverage_count <> 6
    )
   or (
        weather_category_coverage_count = 0
        and (
            weather_latest_issued_at is not null
            or weather_latest_collected_at is not null
            or tmp_value_num is not null
            or pop_value_num is not null
            or reh_value_num is not null
            or wsd_value_num is not null
            or sky_qualitative_code is not null
            or pty_qualitative_code is not null
            or is_precipitating is not null
        )
    )
   or weather_latest_issued_at > observed_at_kst
