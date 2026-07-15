{{ config(severity='warn') }}

{% set warn_hours = env_var('TRAFFIC_INCIDENT_AVAILABILITY_WARN_HOURS', '24') | int %}

with latest_manifest_state as (
    {{ latest_manifest_run_state('traffic_bronze', 'collection_run_manifest', 'seoul_traffic_incident') }}
),

latest_publishable_manifest as (
    select max(manifest_event_at_utc) as manifest_at
    from latest_manifest_state
    where manifest_status = 'SUCCESS'
      and is_publishable
),

latest_incident as (
    select max(cast(collected_at as timestamp(6))) as incident_at
    from {{ source('traffic_bronze', 'seoul_traffic_incident') }}
    where source_id = 'seoul_traffic_incident'
      and result_code = 'INFO-000'
)

select
    manifest_at,
    incident_at,
    {{ warn_hours }} as warn_hours
from latest_publishable_manifest
cross join latest_incident
where manifest_at is not null
  and (
      incident_at is null
      or date_diff('second', incident_at, manifest_at) > {{ warn_hours * 60 * 60 }}
  )
