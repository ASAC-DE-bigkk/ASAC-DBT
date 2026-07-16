-- Serving Gold: current Traffic anchor with no-hindsight Citydata place signals.
-- Each signal timestamp remains separate; the metrics are monitored-place
-- context rather than a resident-population or administrative-dong total.

{{ config(materialized='table') }}

with traffic as (
    select *
    from {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}
),

citydata_candidates as (
    select
        traffic.product_row_id as traffic_product_row_id,
        cast(citydata.area_cd as varchar) as area_cd,
        cast(citydata.area_ppltn_min as double) as area_ppltn_min,
        cast(citydata.area_ppltn_max as double) as area_ppltn_max,
        cast(citydata.payment_count as double) as payment_count,
        cast(citydata.subway_gton_30min as double) as subway_gton_30min,
        cast(citydata.bus_gton_30min as double) as bus_gton_30min,
        cast(citydata.sbike_parking_total as double) as sbike_parking_total,
        cast(citydata.sbike_rack_total as double) as sbike_rack_total,
        cast(citydata.ppltn_at as timestamp(6)) as ppltn_at,
        cast(citydata.cmrcl_at as timestamp(6)) as cmrcl_at,
        cast(citydata.transit_at as timestamp(6)) as transit_at,
        cast(citydata.sbike_at as timestamp(6)) as sbike_at,
        cast(citydata.refreshed_at as timestamp(6)) as refreshed_at
    from traffic
    inner join {{ source('traffic_citydata_gold', 'gold_citydata_place_latest') }} as citydata
        on traffic.admin_dong_code = citydata.admin_dong_code
       and citydata.refreshed_at <= traffic.status_observed_at
),

citydata_by_traffic as (
    select
        traffic_product_row_id,
        count(distinct area_cd) as monitored_place_count,
        avg((area_ppltn_min + area_ppltn_max) / 2) as avg_place_population_proxy,
        max((area_ppltn_min + area_ppltn_max) / 2) as peak_place_population_proxy,
        sum(payment_count) as payment_count_sum,
        sum(subway_gton_30min) as subway_gton_30min_sum,
        sum(bus_gton_30min) as bus_gton_30min_sum,
        sum(sbike_parking_total) as sbike_parking_total_sum,
        sum(sbike_rack_total) as sbike_rack_total_sum,
        max(ppltn_at) as citydata_latest_ppltn_at,
        max(cmrcl_at) as citydata_latest_cmrcl_at,
        max(transit_at) as citydata_latest_transit_at,
        max(sbike_at) as citydata_latest_sbike_at,
        max(refreshed_at) as citydata_latest_refreshed_at
    from citydata_candidates
    group by 1
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
    citydata_by_traffic.traffic_product_row_id is not null as citydata_observation_present,
    citydata_by_traffic.monitored_place_count,
    citydata_by_traffic.avg_place_population_proxy,
    citydata_by_traffic.peak_place_population_proxy,
    citydata_by_traffic.payment_count_sum,
    citydata_by_traffic.subway_gton_30min_sum,
    citydata_by_traffic.bus_gton_30min_sum,
    citydata_by_traffic.sbike_parking_total_sum,
    citydata_by_traffic.sbike_rack_total_sum,
    citydata_by_traffic.citydata_latest_ppltn_at,
    citydata_by_traffic.citydata_latest_cmrcl_at,
    citydata_by_traffic.citydata_latest_transit_at,
    citydata_by_traffic.citydata_latest_sbike_at,
    citydata_by_traffic.citydata_latest_refreshed_at,
    'not_exposed_by_upstream_gold' as external_freshness_status
from traffic
left join citydata_by_traffic
    on traffic.product_row_id = citydata_by_traffic.traffic_product_row_id
