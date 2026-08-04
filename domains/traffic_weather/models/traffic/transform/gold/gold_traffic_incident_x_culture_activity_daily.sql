-- Serving Gold: current Traffic anchor with same-day Culture activity context.
-- Culture's zero rows are meaningful because its published scaffold covers the
-- observed calendar; absent calendar dates remain null and flag false.

{{ config(materialized='table') }}

with traffic as (
    select *
    from {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}
),

culture as (
    select
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(event_date as date) as event_date,
        cast(activities_count as bigint) as activities_count,
        cast(performances_count as bigint) as performances_count,
        cast(events_count as bigint) as events_count,
        cast(kopis_festivals_count as bigint) as kopis_festivals_count,
        cast(exhibitions_count as bigint) as exhibitions_count
    from {{ source('traffic_culture_gold', 'gold_culture_activity_by_dong') }}
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
    culture.admin_dong_code is not null as culture_calendar_present,
    culture.activities_count,
    culture.performances_count,
    culture.events_count,
    culture.kopis_festivals_count,
    culture.exhibitions_count,
    'not_exposed_by_upstream_gold' as external_freshness_status
from traffic
left join culture
    on traffic.admin_dong_code = culture.admin_dong_code
   and cast(traffic.hour_at as date) = culture.event_date
