-- Serving Gold: current Traffic anchor with same-hour Transit context.
-- Grain stays (admin_dong_code, hour_at); missing Transit is explicit rather
-- than interpreted as zero bus, subway, or parking activity.

{{ config(materialized='table') }}

with traffic as (
    select *
    from {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}
),

transit as (
    select
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(hour_at as timestamp(6)) as hour_at,
        max(bus_obs_cnt) as bus_obs_cnt,
        max(bus_veh_cnt) as bus_veh_cnt,
        max(bus_congestion_avg) as bus_congestion_avg,
        max(bus_full_ratio) as bus_full_ratio,
        max(bus_stop_ratio) as bus_stop_ratio,
        max(subway_arrival_cnt) as subway_arrival_cnt,
        max(subway_wait_avg_s) as subway_wait_avg_s,
        max(subway_last_train_cnt) as subway_last_train_cnt,
        max(parking_lot_cnt) as parking_lot_cnt,
        max(parking_occupancy_avg) as parking_occupancy_avg,
        max(parking_full_lot_cnt) as parking_full_lot_cnt
    from {{ source('traffic_transit_gold', 'gold_transit_dong_hourly') }}
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
    transit.admin_dong_code is not null as transit_observation_present,
    transit.bus_obs_cnt is not null as bus_observation_present,
    transit.subway_arrival_cnt is not null as subway_observation_present,
    transit.parking_lot_cnt is not null as parking_observation_present,
    transit.bus_obs_cnt,
    transit.bus_veh_cnt,
    transit.bus_congestion_avg,
    transit.bus_full_ratio,
    transit.bus_stop_ratio,
    transit.subway_arrival_cnt,
    transit.subway_wait_avg_s,
    transit.subway_last_train_cnt,
    transit.parking_lot_cnt,
    transit.parking_occupancy_avg,
    transit.parking_full_lot_cnt,
    'not_exposed_by_upstream_gold' as external_freshness_status
from traffic
left join transit
    on traffic.admin_dong_code = transit.admin_dong_code
   and traffic.hour_at = transit.hour_at
