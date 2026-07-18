{{ config(tags=['traffic_gold_gate']) }}

with eligible_weather as (
    select
        traffic.product_row_id,
        max(cast(weather.issued_at as timestamp(6))) as expected_latest_issued_at
    from {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }} as traffic
    inner join {{ ref('asac_seoul', 'gold_weather_forecast_by_admin_dong') }} as weather
        on cast(traffic.admin_dong_code as varchar) = cast(weather.admin_dong_code as varchar)
       and cast(date_trunc('hour', weather.forecast_at) as timestamp(6))
            = cast(traffic.hour_at as timestamp(6))
       and cast(weather.issued_at as timestamp(6))
            <= cast(traffic.status_observed_at as timestamp(6))
    where lower(cast(weather.category as varchar)) in ('tmp', 'pop', 'reh', 'wsd', 'sky', 'pty')
    group by traffic.product_row_id
),

gold as (
    select
        product_row_id,
        weather_latest_issued_at
    from {{ ref('gold_traffic_incident_x_weather_current_hourly') }}
    where weather_category_coverage_count is not null
)

select
    gold.product_row_id,
    gold.weather_latest_issued_at,
    eligible_weather.expected_latest_issued_at
from gold
left join eligible_weather
    on gold.product_row_id = eligible_weather.product_row_id
where eligible_weather.product_row_id is null
   or gold.weather_latest_issued_at is distinct from eligible_weather.expected_latest_issued_at
