-- Serving Gold: current Traffic anchor with scheduled, dong-precise events
-- active on the same calendar day.  It never promotes gu-only events to dong
-- precision, preventing spatial fan-out.

{{ config(materialized='table') }}

with traffic as (
    select *
    from {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}
),

event_days as (
    select
        cast(event.admin_dong_code as varchar) as admin_dong_code,
        cast(event.event_ref as varchar) as event_ref,
        cast(event.event_type as varchar) as event_type,
        cast(event.is_free as varchar) as is_free,
        cast(day.event_date as date) as event_date
    from {{ source('traffic_culture_gold', 'gold_culture_event_schedule') }} as event
    cross join unnest(sequence(event.event_start_date, event.event_end_date)) as day(event_date)
    where event.admin_dong_code is not null
      and event.quality_status = 'dong_precise'
),

events_by_day as (
    select
        admin_dong_code,
        event_date,
        count(distinct event_ref) as scheduled_event_count,
        count(distinct event_type) as scheduled_event_type_count,
        count_if(is_free is not null) as price_disclosed_event_count
    from event_days
    group by 1, 2
)

select
    traffic.product_row_id,
    traffic.admin_dong_code,
    traffic.hour_at,
    traffic.admin_dong,
    traffic.gu_code,
    traffic.gu,
    traffic.admin_dong_revision_date,
    traffic.incident_count,
    traffic.has_incident,
    traffic.quality_state,
    traffic.snapshot_as_of_at,
    traffic.status_observed_at,
    traffic.published_at,
    traffic.snapshot_dag_run_id,
    traffic.source_id,
    cast(traffic.hour_at as date) as context_date,
    events_by_day.admin_dong_code is not null as culture_schedule_observation_present,
    events_by_day.scheduled_event_count,
    events_by_day.scheduled_event_type_count,
    events_by_day.price_disclosed_event_count,
    'not_exposed_by_upstream_gold' as external_freshness_status
from traffic
left join events_by_day
    on traffic.admin_dong_code = events_by_day.admin_dong_code
   and cast(traffic.hour_at as date) = events_by_day.event_date
