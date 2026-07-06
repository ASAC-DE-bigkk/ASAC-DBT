with place_grid as (
    select
        place_id,
        place_name,
        alias_names,
        gu,
        admin_dong,
        latitude,
        longitude,
        nx,
        ny,
        mapping_method,
        grid_distance_m,
        source_admin_code
    from {{ ref('dim_weather_place') }}
),

forecast as (
    select
        request_id,
        source_id,
        request_params_json,
        place_id as source_grid_place_id,
        nx,
        ny,
        category,
        issued_at,
        forecast_at,
        time_bucket,
        fcst_value_raw,
        fcst_value_num,
        raw_object_key,
        payload_hash,
        total_count,
        item_count,
        load_date,
        collected_at,
        dag_run_id
    from {{ ref('silver_kma_vilage_fcst') }}
),

ranked_forecast as (
    select
        *,
        row_number() over (
            partition by nx, ny, forecast_at, category
            order by
                issued_at desc,
                collected_at desc,
                raw_object_key desc,
                request_id desc
        ) as row_num
    from forecast
),

latest_forecast as (
    select
        request_id,
        source_id,
        request_params_json,
        source_grid_place_id,
        nx,
        ny,
        category,
        issued_at,
        forecast_at,
        time_bucket,
        fcst_value_raw,
        fcst_value_num,
        raw_object_key,
        payload_hash,
        total_count,
        item_count,
        load_date,
        collected_at,
        dag_run_id
    from ranked_forecast
    where row_num = 1
),

place_forecast as (
    select
        place_grid.place_id,
        place_grid.place_name,
        place_grid.alias_names,
        place_grid.gu,
        place_grid.admin_dong,
        place_grid.latitude,
        place_grid.longitude,
        place_grid.nx,
        place_grid.ny,
        place_grid.mapping_method,
        place_grid.grid_distance_m,
        place_grid.source_admin_code,
        latest_forecast.source_grid_place_id,
        latest_forecast.request_id,
        latest_forecast.source_id,
        latest_forecast.request_params_json,
        latest_forecast.category,
        latest_forecast.issued_at,
        latest_forecast.forecast_at,
        latest_forecast.time_bucket,
        latest_forecast.fcst_value_raw,
        latest_forecast.fcst_value_num,
        latest_forecast.raw_object_key,
        latest_forecast.payload_hash,
        latest_forecast.total_count,
        latest_forecast.item_count,
        latest_forecast.load_date,
        latest_forecast.collected_at,
        latest_forecast.dag_run_id
    from latest_forecast
    inner join place_grid
        on latest_forecast.nx = place_grid.nx
       and latest_forecast.ny = place_grid.ny
)

select
    place_id,
    place_name,
    alias_names,
    gu,
    admin_dong,
    latitude,
    longitude,
    nx,
    ny,
    mapping_method,
    grid_distance_m,
    source_admin_code,
    source_grid_place_id,
    request_id,
    source_id,
    request_params_json,
    category,
    issued_at,
    forecast_at,
    time_bucket,
    fcst_value_raw,
    fcst_value_num,
    raw_object_key,
    payload_hash,
    total_count,
    item_count,
    load_date,
    collected_at,
    dag_run_id
from place_forecast
