-- Gold: current incidents enriched with the pinned per-link TrafficInfo snapshot.
-- The incident side is the driving relation so a missing flow response never
-- removes a valid incident from the final query surface.

{{ config(materialized='table') }}

{% set flow_snapshot_dag_run_id = var('traffic_flow_snapshot_dag_run_id', '') or '' %}

with flow_ranked as (
    select
        flow.*,
        row_number() over (
            partition by flow.link_id
            order by flow.collected_at desc, flow.raw_object_key desc, flow.request_id desc
        ) as row_num
    from {{ ref('silver_seoul_traffic_flow') }} as flow
    where cast(flow.dag_run_id as varchar) = '{{ flow_snapshot_dag_run_id | replace("'", "''") }}'
),

current_flow as (
    select *
    from flow_ranked
    where row_num = 1
),

incidents as (
    select
        incident.source_record_id,
        incident.source_id as incident_source_id,
        incident.acc_type,
        incident.acc_dtype,
        incident.asset_id as link_id,
        incident.acc_road_code,
        incident.acc_info,
        incident.occurred_at,
        incident.expected_clear_at,
        incident.time_bucket,
        incident.raw_object_key as incident_raw_object_key,
        incident.payload_hash as incident_payload_hash,
        incident.collected_at as incident_collected_at,
        incident.dag_run_id as incident_dag_run_id
    from {{ ref('silver_seoul_traffic_incident_current') }} as incident
)

select
    incidents.source_record_id,
    incidents.incident_source_id,
    incidents.acc_type,
    incidents.acc_dtype,
    incidents.link_id,
    incidents.acc_road_code,
    incidents.acc_info,
    incidents.occurred_at,
    incidents.expected_clear_at,
    incidents.time_bucket,
    incidents.incident_raw_object_key,
    incidents.incident_payload_hash,
    incidents.incident_collected_at,
    incidents.incident_dag_run_id,
    current_flow.flow_speed,
    current_flow.flow_travel_time,
    current_flow.flow_value_quality,
    current_flow.observed_at as flow_observed_at,
    current_flow.raw_object_key as flow_raw_object_key,
    current_flow.payload_hash as flow_payload_hash,
    current_flow.dag_run_id as flow_dag_run_id,
    case
        when current_flow.link_id is not null then 'matched'
        else 'missing_flow'
    end as flow_match_status
from incidents
left join current_flow
    on incidents.link_id = current_flow.link_id
