with expected_context as (
    select
        weather.admin_dong_code,
        weather.forecast_date,
        culture.activities_count
    from {{ ref('gold_weather_daily_by_admin_dong') }} as weather
    left join {{ source('culture_gold', 'gold_culture_activity_by_dong') }} as culture
        on weather.admin_dong_code = culture.admin_dong_code
       and weather.forecast_date = culture.event_date
),

missing_context as (
    select
        expected_context.admin_dong_code,
        expected_context.forecast_date,
        'missing_model_row' as failure_reason
    from expected_context
    left join {{ ref('gold_weather_x_culture_activity_daily') }} as model
        on expected_context.admin_dong_code = model.admin_dong_code
       and expected_context.forecast_date = model.forecast_date
    where model.admin_dong_code is null
),

bad_presence as (
    select
        model.admin_dong_code,
        model.forecast_date,
        'bad_zero_or_null_semantics' as failure_reason
    from {{ ref('gold_weather_x_culture_activity_daily') }} as model
    left join expected_context
        on model.admin_dong_code = expected_context.admin_dong_code
       and model.forecast_date = expected_context.forecast_date
    where (expected_context.activities_count is null and (model.culture_observation_present or model.activities_count is not null))
       or (expected_context.activities_count is not null and (not model.culture_observation_present or model.activities_count <> expected_context.activities_count))
)

select * from missing_context
union all
select * from bad_presence
