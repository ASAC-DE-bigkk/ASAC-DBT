-- silver: expand each KMA grid forecast to the admin-dong places assigned to
-- that grid. The source Grid Silver remains intact because one 5km grid can
-- serve multiple admin dongs.

-- incremental 전환(#147, DL-013 후속): 매 run 24M행 풀 리빌드를 상류(#145)와 동일한
-- collected_at 워터마크 증분으로 교체. views_enabled/on_table_exists 는 R2 카탈로그
-- 유령 뷰 409 우회(#70 선례). dim_weather_place 매핑 변경은 증분 경로에 소급 반영되지
-- 않으므로 매핑 변경 시 --full-refresh 로 재빌드할 것 — 이 모델은 순수 조인이라
-- full-refresh 가 안전하다(silver_kma_vilage_fcst 의 full-refresh 금지와 다름).

-- merge 소스 dedup(#340): 이 모델만 형제 merge 모델(silver_kma_vilage_fcst,
-- silver_kma_vilage_fcst_grid, gold_weather_forecast_by_place, traffic flow 계열)과 달리
-- MERGE 소스에 grain 유일성 보장이 없었다. #104(ppltn/citydata)에서 동일 유형 결함이
-- 실제 중복 누적으로 관측된 선례가 있어, 같은 컨벤션(collected_at desc, raw_object_key
-- desc, request_id desc 우선)으로 winner를 선택한다. place_id는 정확히 하나의
-- grid에만 매핑되므로, fan-out 전에 grid grain에서 max_by로 winner를 결정해 wide
-- payload window와 source 재조인으로 인한 Trino HashBuilder 메모리 초과를 피한다.
{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['place_id', 'issued_at', 'forecast_at', 'category'],
    on_schema_change='fail',
    views_enabled=false,
    on_table_exists='drop',
) }}

{% set snapshot_dag_run_id = var('weather_snapshot_dag_run_id', '') | string | trim %}
{% set historical_transform = var('weather_historical_transform', false) %}

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
    {% if historical_transform %}
    where dag_run_id = '{{ snapshot_dag_run_id | replace("'", "''") }}'
    {% elif is_incremental() %}
    where collected_at >= (
        select coalesce(max(collected_at), timestamp '1970-01-01 00:00:00')
               - interval '{{ weather_w1_lookback_minutes() }}' minute
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
),

-- OOM 방지: place fan-out 전에 native grid grain의 winner 하나만 유지한다.
-- max_by의 sort key는 기존 row_number ORDER BY와 동일한 우선순위다.
selected_grid_forecast as (
    select
        nx,
        ny,
        category,
        issued_at,
        forecast_at,
        (winner)[1] as request_id,
        (winner)[2] as source_id,
        (winner)[3] as request_params_json,
        (winner)[4] as source_grid_place_id,
        (winner)[5] as event_at,
        (winner)[6] as time_bucket,
        (winner)[7] as fcst_value_raw,
        (winner)[8] as fcst_value_num,
        (winner)[9] as raw_object_key,
        (winner)[10] as payload_hash,
        (winner)[11] as total_count,
        (winner)[12] as item_count,
        (winner)[13] as load_date,
        (winner)[14] as collected_at,
        (winner)[15] as dag_run_id
    from (
        select
            nx,
            ny,
            category,
            issued_at,
            forecast_at,
            max_by(
                row(
                    request_id,
                    source_id,
                    request_params_json,
                    source_grid_place_id,
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
                ),
                row(collected_at, raw_object_key, request_id)
            ) as winner
        from grid_forecast
        group by nx, ny, category, issued_at, forecast_at
    ) ranked_grid
),

joined_payload as (
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
    from selected_grid_forecast as grid_forecast
    inner join place_grid
        on grid_forecast.nx = place_grid.nx
       and grid_forecast.ny = place_grid.ny
)

select
    request_id,
    source_id,
    request_params_json,
    place_id,
    place_name,
    alias_names,
    gu,
    admin_dong,
    latitude,
    longitude,
    admin_dong_code,
    gu_code,
    source_admin_code,
    source_grid_place_id,
    nx,
    ny,
    mapping_method,
    grid_distance_m,
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
from joined_payload
