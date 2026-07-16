with expected_context as (
    select
        weather.admin_dong_code,
        weather.forecast_date,
        commerce.latest_collected_at
    from {{ ref('gold_weather_daily_by_admin_dong') }} as weather
    left join {{ source('commerce_gold', 'gold_license_dong_summary') }} as commerce
        on weather.admin_dong_code = commerce.admin_dong_code
       and date(commerce.latest_collected_at) <= weather.forecast_date
),

missing_context as (
    select
        expected_context.admin_dong_code,
        expected_context.forecast_date,
        'missing_model_row' as failure_reason
    from expected_context
    left join {{ ref('gold_weather_x_commerce_business_exposure_daily') }} as model
        on expected_context.admin_dong_code = model.admin_dong_code
       and expected_context.forecast_date = model.forecast_date
    where model.admin_dong_code is null
),

bad_as_of as (
    select
        model.admin_dong_code,
        model.forecast_date,
        'bad_as_of' as failure_reason
    from {{ ref('gold_weather_x_commerce_business_exposure_daily') }} as model
    left join expected_context
        on model.admin_dong_code = expected_context.admin_dong_code
       and model.forecast_date = expected_context.forecast_date
    where (expected_context.latest_collected_at is null and (model.commerce_observation_present or model.commerce_latest_collected_at is not null))
       or (
           expected_context.latest_collected_at is not null
           and (
               not model.commerce_observation_present
               or model.commerce_latest_collected_at <> expected_context.latest_collected_at
               or date(model.commerce_latest_collected_at) > model.forecast_date
           )
       )
)

select * from missing_context
union all
select * from bad_as_of
