-- gold: latest KMA forecast mart by admin-dong place_id, forecast_at, category.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['place_id', 'forecast_at', 'category'],
    on_schema_change='fail',
) }}

{% set snapshot_dag_run_id = var('weather_snapshot_dag_run_id', '') | string | trim %}
{% set historical_transform = var('weather_historical_transform', false) %}

with
{% if historical_transform %}
affected_grains as (
    select distinct place_id, forecast_at, category
    from {{ ref('silver_weather_forecast_by_admin_dong') }}
    where dag_run_id = '{{ snapshot_dag_run_id | replace("'", "''") }}'
),
{% endif %}
ranked_forecast as (
    select
        *,
        row_number() over (
            partition by place_id, forecast_at, category
            order by
                issued_at desc,
                collected_at desc,
                raw_object_key desc,
                request_id desc
        ) as row_num
    from {{ ref('silver_weather_forecast_by_admin_dong') }}
    {% if historical_transform %}
    inner join affected_grains using (place_id, forecast_at, category)
    {% elif is_incremental() %}
    where collected_at >= (
        select coalesce(max(collected_at), timestamp '1970-01-01') - interval '30' minute
        from {{ this }}
    )
    {% endif %}
)

select
    place_id,
    place_name,
    alias_names,
    gu,
    admin_dong,
    latitude,
    longitude,
    admin_dong_code,
    gu_code,
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
from ranked_forecast
where row_num = 1
