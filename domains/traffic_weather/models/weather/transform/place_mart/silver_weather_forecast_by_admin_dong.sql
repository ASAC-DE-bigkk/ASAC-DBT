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
-- desc, request_id desc 우선)으로 row_number dedup을 추가한다.
{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['place_id', 'issued_at', 'forecast_at', 'category'],
    on_schema_change='fail',
    views_enabled=false,
    on_table_exists='drop',
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
)

select
    ranked.request_id,
    ranked.source_id,
    ranked.request_params_json,
    ranked.place_id,
    ranked.place_name,
    ranked.alias_names,
    ranked.gu,
    ranked.admin_dong,
    ranked.latitude,
    ranked.longitude,
    ranked.admin_dong_code,
    ranked.gu_code,
    ranked.source_admin_code,
    ranked.source_grid_place_id,
    ranked.nx,
    ranked.ny,
    ranked.mapping_method,
    ranked.grid_distance_m,
    ranked.category,
    ranked.issued_at,
    ranked.forecast_at,
    ranked.event_at,
    ranked.time_bucket,
    ranked.fcst_value_raw,
    ranked.fcst_value_num,
    ranked.raw_object_key,
    ranked.payload_hash,
    ranked.total_count,
    ranked.item_count,
    ranked.load_date,
    ranked.collected_at,
    ranked.dag_run_id
from (
    select
        joined.*,
        row_number() over (
            partition by
                joined.place_id,
                joined.issued_at,
                joined.forecast_at,
                joined.category
            order by
                joined.collected_at desc,
                joined.raw_object_key desc,
                joined.request_id desc
        ) as _rn
    from (
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
    ) joined
) ranked
where ranked._rn = 1
