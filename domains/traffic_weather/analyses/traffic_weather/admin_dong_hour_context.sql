-- Read-only cross-domain recipe. dbt compiles analyses but never materializes them.
-- Output grain: admin_dong_code x traffic hour_at x weather forecast_at x category.
-- Join only canonical public producers; neither domain's Silver or compatibility Gold is public.
with traffic_hour as (
    select
        product_row_id,
        admin_dong_code,
        admin_dong_revision_date,
        hour_at,
        incident_count,
        has_incident,
        quality_state as traffic_quality_state,
        snapshot_as_of_at as traffic_snapshot_as_of_at
    from {{ ref('asac_seoul', 'gold_traffic_incident_current_by_admin_dong_hourly') }}
    where quality_state in ('complete', 'complete_zero')
),

weather_forecast as (
    select
        product_row_id,
        admin_dong_code,
        admin_dong_revision_date,
        forecast_at,
        category,
        fcst_value_raw,
        value_num,
        value_representation,
        qualitative_code,
        issued_at as weather_issued_at,
        published_at as weather_published_at
    from {{ ref('asac_seoul', 'gold_weather_forecast_by_admin_dong') }}
)

select
    traffic_hour.product_row_id as traffic_product_row_id,
    weather_forecast.product_row_id as weather_product_row_id,
    traffic_hour.admin_dong_code,
    traffic_hour.admin_dong_revision_date,
    traffic_hour.hour_at as context_hour_at,
    weather_forecast.forecast_at,
    weather_forecast.category,
    traffic_hour.incident_count,
    traffic_hour.has_incident,
    traffic_hour.traffic_quality_state,
    traffic_hour.traffic_snapshot_as_of_at,
    weather_forecast.fcst_value_raw,
    weather_forecast.value_num as forecast_value_num,
    weather_forecast.value_representation as forecast_value_representation,
    weather_forecast.qualitative_code,
    weather_forecast.weather_issued_at,
    weather_forecast.weather_published_at
from traffic_hour
inner join weather_forecast
    on traffic_hour.admin_dong_code = weather_forecast.admin_dong_code
    and traffic_hour.admin_dong_revision_date
        = weather_forecast.admin_dong_revision_date
    and weather_forecast.forecast_at >= traffic_hour.hour_at
    and weather_forecast.forecast_at < traffic_hour.hour_at + interval '1' hour
