{{ config(tags=['traffic_gold_gate']) }}

with weather_bridge as (
    select
        cast(source_admin_code as varchar) as admin_dong_code,
        cast(nx as integer) as nx,
        cast(ny as integer) as ny
    from {{ ref('bridge_weather_admin_dong_grid') }}
    where cast(bridge_version as varchar) = 'weather_admin_dong_grid_bridge_v1'
      and cast(canonical_join_eligible as boolean)
),

eligible_weather as (
    select
        traffic.product_row_id,
        count(distinct lower(cast(weather.category as varchar)))
            as expected_category_coverage_count,
        max(cast(weather.issued_at as timestamp(6))) as expected_latest_issued_at
    from {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }} as traffic
    inner join weather_bridge
        on cast(traffic.admin_dong_code as varchar) = weather_bridge.admin_dong_code
    inner join {{ ref('silver_kma_vilage_fcst_grid') }} as weather
        on weather_bridge.nx = cast(weather.nx as integer)
       and weather_bridge.ny = cast(weather.ny as integer)
       and cast(date_trunc('hour', weather.forecast_at) as timestamp(6))
            = cast(traffic.hour_at as timestamp(6))
       and cast(weather.issued_at as timestamp(6))
            <= cast(traffic.status_observed_at as timestamp(6))
    where weather.issued_at is not null
      and lower(cast(weather.category as varchar)) in ('tmp', 'pop', 'reh', 'wsd', 'sky', 'pty')
    group by traffic.product_row_id
),

gold as (
    select
        product_row_id,
        weather_category_coverage_count,
        weather_latest_issued_at
    from {{ ref('gold_traffic_incident_x_weather_current_hourly') }}
)

select
    coalesce(gold.product_row_id, eligible_weather.product_row_id) as product_row_id,
    gold.weather_category_coverage_count,
    eligible_weather.expected_category_coverage_count,
    gold.weather_latest_issued_at,
    eligible_weather.expected_latest_issued_at
from gold
full outer join eligible_weather
    on gold.product_row_id = eligible_weather.product_row_id
where gold.product_row_id is null
   or (
        eligible_weather.product_row_id is null
        and (
            gold.weather_category_coverage_count is not null
            or gold.weather_latest_issued_at is not null
        )
    )
   or (
        eligible_weather.product_row_id is not null
        and (
            gold.weather_category_coverage_count is distinct from
                eligible_weather.expected_category_coverage_count
            or gold.weather_latest_issued_at is distinct from
                eligible_weather.expected_latest_issued_at
        )
    )
