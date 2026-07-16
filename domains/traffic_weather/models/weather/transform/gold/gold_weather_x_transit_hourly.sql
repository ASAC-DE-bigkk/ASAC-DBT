with weather as (
    select
        wide.product_row_id as weather_wide_product_row_id,
        wide.admin_dong_code,
        wide.forecast_at as hour_at,
        wide.admin_dong,
        wide.gu_code,
        wide.gu,
        wide.temp_c,
        wide.humidity_pct,
        wide.wind_ms,
        wide.wind_dir_deg,
        wide.precip_prob_pct,
        wide.sky_code,
        wide.sky_label,
        wide.pty_code,
        wide.pty_label,
        wide.is_precipitating,
        wide.pcp_raw,
        wide.pcp_representation,
        wide.pcp_mm,
        wide.pcp_lower_mm,
        wide.pcp_upper_mm,
        wide.sno_raw,
        wide.sno_representation,
        wide.sno_cm,
        wide.forecast_lead_hours
    from {{ ref('gold_weather_forecast_wide_by_admin_dong') }} as wide
),

weather_lineage as (
    select
        admin_dong_code,
        forecast_at as hour_at,
        min(issued_at) as weather_issued_at_min,
        max(issued_at) as weather_issued_at_max,
        max(collected_at) as weather_collected_at_max,
        max(published_at) as weather_published_at_max
    from {{ ref('gold_weather_forecast_by_admin_dong') }}
    group by admin_dong_code, forecast_at
),

transit as (
    select
        admin_dong_code,
        hour_at,
        bus_obs_cnt,
        bus_veh_cnt,
        bus_congestion_avg,
        bus_full_ratio,
        bus_stop_ratio,
        subway_arrival_cnt,
        subway_wait_avg_s,
        subway_last_train_cnt,
        parking_lot_cnt,
        parking_occupancy_avg,
        parking_full_lot_cnt
    from {{ source('transit_gold', 'gold_transit_dong_hourly') }}
)

select
    concat(weather.admin_dong_code, '|', to_iso8601(cast(weather.hour_at as timestamp(6)))) as product_row_id,
    weather.admin_dong_code,
    weather.hour_at,
    weather.admin_dong,
    weather.gu_code,
    weather.gu,
    weather.temp_c,
    weather.humidity_pct,
    weather.wind_ms,
    weather.wind_dir_deg,
    weather.precip_prob_pct,
    weather.sky_code,
    weather.sky_label,
    weather.pty_code,
    weather.pty_label,
    weather.is_precipitating,
    weather.pcp_raw,
    weather.pcp_representation,
    weather.pcp_mm,
    weather.pcp_lower_mm,
    weather.pcp_upper_mm,
    weather.sno_raw,
    weather.sno_representation,
    weather.sno_cm,
    weather.forecast_lead_hours,
    weather_lineage.weather_issued_at_min,
    weather_lineage.weather_issued_at_max,
    weather_lineage.weather_collected_at_max,
    weather_lineage.weather_published_at_max,
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
    'not_exposed_by_upstream_gold' as external_freshness_status,
    weather.weather_wide_product_row_id
from weather
left join weather_lineage
    on weather.admin_dong_code = weather_lineage.admin_dong_code
   and weather.hour_at = weather_lineage.hour_at
left join transit
    on weather.admin_dong_code = transit.admin_dong_code
   and weather.hour_at = transit.hour_at
