with weather_anchor as (
    select admin_dong_code, forecast_at as hour_at
    from {{ ref('gold_weather_forecast_wide_by_admin_dong') }}
),

model_anchor as (
    select admin_dong_code, hour_at
    from {{ ref('gold_weather_x_transit_hourly') }}
),

missing_context as (
    select weather_anchor.*, 'missing_model_row' as failure_reason
    from weather_anchor
    left join model_anchor
        on weather_anchor.admin_dong_code = model_anchor.admin_dong_code
       and weather_anchor.hour_at = model_anchor.hour_at
    where model_anchor.admin_dong_code is null
),

extra_context as (
    select model_anchor.*, 'extra_model_row' as failure_reason
    from model_anchor
    left join weather_anchor
        on model_anchor.admin_dong_code = weather_anchor.admin_dong_code
       and model_anchor.hour_at = weather_anchor.hour_at
    where weather_anchor.admin_dong_code is null
)

select * from missing_context
union all
select * from extra_context
