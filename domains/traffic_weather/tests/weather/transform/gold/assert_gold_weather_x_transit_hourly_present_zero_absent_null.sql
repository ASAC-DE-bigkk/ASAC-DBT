with expected_context as (
    select
        weather.admin_dong_code,
        weather.forecast_at as hour_at,
        transit.bus_obs_cnt,
        transit.subway_arrival_cnt,
        transit.parking_lot_cnt
    from {{ ref('gold_weather_forecast_wide_by_admin_dong') }} as weather
    left join {{ source('transit_gold', 'gold_transit_dong_hourly') }} as transit
        on weather.admin_dong_code = transit.admin_dong_code
       and weather.forecast_at = transit.hour_at
),

missing_context as (
    select
        expected_context.admin_dong_code,
        expected_context.hour_at,
        'missing_model_row' as failure_reason
    from expected_context
    left join {{ ref('gold_weather_x_transit_hourly') }} as model
        on expected_context.admin_dong_code = model.admin_dong_code
       and expected_context.hour_at = model.hour_at
    where model.admin_dong_code is null
),

bad_presence as (
    select
        model.admin_dong_code,
        model.hour_at,
        'bad_zero_or_null_semantics' as failure_reason
    from {{ ref('gold_weather_x_transit_hourly') }} as model
    left join expected_context
        on model.admin_dong_code = expected_context.admin_dong_code
       and model.hour_at = expected_context.hour_at
    where (expected_context.bus_obs_cnt is null and model.bus_obs_cnt is not null)
       or (expected_context.bus_obs_cnt is not null and model.bus_obs_cnt <> expected_context.bus_obs_cnt)
       or (expected_context.subway_arrival_cnt is null and model.subway_arrival_cnt is not null)
       or (expected_context.subway_arrival_cnt is not null and model.subway_arrival_cnt <> expected_context.subway_arrival_cnt)
       or (expected_context.parking_lot_cnt is null and model.parking_lot_cnt is not null)
       or (expected_context.parking_lot_cnt is not null and model.parking_lot_cnt <> expected_context.parking_lot_cnt)
)

select * from missing_context
union all
select * from bad_presence
