-- Serving Gold: current Traffic anchor with no-hindsight Commerce stock.
-- Business counts are establishment stock, not same-hour footfall or causality.

{{ config(materialized='table') }}

with traffic as (
    select *
    from {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}
),

commerce as (
    select
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(business_count as bigint) as business_count,
        cast(business_open_count as bigint) as business_open_count,
        cast(business_closed_count as bigint) as business_closed_count,
        cast(dataset_count as bigint) as dataset_count,
        cast(geocoded_count as bigint) as geocoded_count,
        cast(latest_collected_at as timestamp(6)) as latest_collected_at
    from {{ source('traffic_commerce_gold', 'gold_license_dong_summary') }}
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
    commerce.admin_dong_code is not null as commerce_observation_present,
    commerce.business_count,
    commerce.business_open_count,
    commerce.business_closed_count,
    commerce.dataset_count,
    commerce.geocoded_count,
    commerce.latest_collected_at as commerce_latest_collected_at,
    'not_exposed_by_upstream_gold' as external_freshness_status
from traffic
left join commerce
    on traffic.admin_dong_code = commerce.admin_dong_code
   and commerce.latest_collected_at <= traffic.status_observed_at
