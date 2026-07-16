-- Serving Gold: the latest publishable TOPIS incident snapshot.
-- Grain: source_record_id.  The source is already pinned by the transform DAG,
-- so this model does not silently substitute a newer collection run.

{{ config(materialized='table') }}

select
    cast(incident.source_record_id as varchar) as source_record_id,
    cast(incident.source_id as varchar) as source_id,
    cast(incident.acc_type as varchar) as acc_type,
    cast(incident.acc_dtype as varchar) as acc_dtype,
    cast(incident.asset_id as varchar) as link_id,
    cast(incident.acc_road_code as varchar) as acc_road_code,
    cast(incident.acc_info as varchar) as acc_info,
    cast(incident.source_coordinate_system as varchar) as source_coordinate_system,
    cast(incident.source_location_quality as varchar) as source_location_quality,
    cast(incident.longitude as double) as longitude,
    cast(incident.latitude as double) as latitude,
    cast(incident.admin_dong_code as varchar) as admin_dong_code,
    cast(incident.gu_code as varchar) as gu_code,
    cast(incident.admin_dong as varchar) as admin_dong,
    cast(incident.gu as varchar) as gu,
    cast(incident.occurred_at as timestamp(6)) as occurred_at,
    cast(incident.event_at as timestamp(6)) as event_at,
    cast(incident.expected_clear_at as timestamp(6)) as expected_clear_at,
    cast(incident.valid_from as timestamp(6)) as valid_from,
    cast(incident.valid_to as timestamp(6)) as valid_to,
    cast(incident.time_bucket as timestamp(6)) as time_bucket,
    cast(incident.raw_object_key as varchar) as raw_object_key,
    cast(incident.payload_hash as varchar) as payload_hash,
    cast(incident.collected_at as timestamp(6)) as collected_at_utc,
    cast({{ asac_axes.utc_to_kst('incident.collected_at') }} as timestamp(6)) as snapshot_observed_at,
    cast(incident.dag_run_id as varchar) as snapshot_dag_run_id
from {{ ref('silver_seoul_traffic_incident_current') }} as incident
