with weather_anchor as (
    select admin_dong_code, forecast_date
    from {{ ref('gold_weather_daily_by_admin_dong') }}
),

model_anchor as (
    select admin_dong_code, forecast_date
    from {{ ref('gold_weather_x_commerce_business_exposure_daily') }}
),

missing_context as (
    select weather_anchor.*, 'missing_model_row' as failure_reason
    from weather_anchor
    left join model_anchor
        on weather_anchor.admin_dong_code = model_anchor.admin_dong_code
       and weather_anchor.forecast_date = model_anchor.forecast_date
    where model_anchor.admin_dong_code is null
),

extra_context as (
    select model_anchor.*, 'extra_model_row' as failure_reason
    from model_anchor
    left join weather_anchor
        on model_anchor.admin_dong_code = weather_anchor.admin_dong_code
       and model_anchor.forecast_date = weather_anchor.forecast_date
    where weather_anchor.admin_dong_code is null
)

select * from missing_context
union all
select * from extra_context
