-- silver: expand each KMA grid forecast to the admin-dong places assigned to
-- that grid. The source Grid Silver remains intact because one 5km grid can
-- serve multiple admin dongs.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['place_id', 'issued_at', 'forecast_at', 'category']
) }}

with grid_forecast as (
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
        event_at,
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
    {% if is_incremental() %}
    where collected_at >= (
        select coalesce(max(collected_at), timestamp '1970-01-01') - interval '30' minute
        from {{ this }}
    )
    {% endif %}
),

place_grid as (
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
        admin_dong_code,
        gu_code
    from {{ ref('dim_weather_place') }}
)

select
    grid_forecast.request_id,
    grid_forecast.source_id,
    grid_forecast.request_params_json,
    place_grid.place_id,
    place_grid.place_name,
    place_grid.alias_names,
    place_grid.gu,
    place_grid.admin_dong,
    place_grid.latitude,
    place_grid.longitude,
    place_grid.admin_dong_code,
    place_grid.gu_code,
    place_grid.source_admin_code,
    grid_forecast.source_grid_place_id,
    grid_forecast.nx,
    grid_forecast.ny,
    place_grid.mapping_method,
    place_grid.grid_distance_m,
    grid_forecast.category,
    grid_forecast.issued_at,
    grid_forecast.forecast_at,
    grid_forecast.event_at,
    grid_forecast.time_bucket,
    grid_forecast.fcst_value_raw,
    grid_forecast.fcst_value_num,
    grid_forecast.raw_object_key,
    grid_forecast.payload_hash,
    grid_forecast.total_count,
    grid_forecast.item_count,
    grid_forecast.load_date,
    grid_forecast.collected_at,
    grid_forecast.dag_run_id
from grid_forecast
inner join place_grid
    on grid_forecast.nx = place_grid.nx
   and grid_forecast.ny = place_grid.ny
