-- depends_on: {{ ref('gold_weather_forecast_by_admin_dong') }}
-- depends_on: {{ ref('bridge_weather_admin_dong_grid') }}
-- depends_on: {{ ref('asac_axes', 'dim_admin_dong') }}
-- depends_on: {{ ref('silver_kma_vilage_fcst_grid') }}

{% set canonical_contract = weather_w2_canonical_contract() %}

{% if weather_w2_is_repair() %}
with eligible_manifest_anchors as (
    {{ weather_w2_latest_publishable_anchors_sql() }}
),

active_bridge as (
    select
        cast(source_admin_code as varchar) as admin_dong_code,
        cast(nx as integer) as nx,
        cast(ny as integer) as ny
    from {{ ref('bridge_weather_admin_dong_grid') }}
    where cast(bridge_version as varchar) = 'weather_admin_dong_grid_bridge_v1'
),

canonical as (
    select cast(admin_dong_code as varchar) as admin_dong_code
    from {{ ref('asac_axes', 'dim_admin_dong') }}
    where cast(revision_date as date) = date '{{ canonical_contract['revision_date'] }}'
),

grid_candidates as (
    select
        cast(grid.nx as integer) as nx,
        cast(grid.ny as integer) as ny,
        cast(grid.forecast_at as timestamp(6)) as forecast_at,
        cast(grid.category as varchar) as category,
        cast(grid.issued_at as timestamp(6)) as issued_at,
        cast(grid.collected_at as timestamp(6)) as collected_at,
        cast(grid.raw_object_key as varchar) as raw_object_key,
        cast(grid.request_id as varchar) as request_id,
        cast(grid.selected_dag_run_id as varchar) as dag_run_id,
        cast(grid.source_grid_place_id as varchar) as source_grid_place_id
    from {{ ref('silver_kma_vilage_fcst_grid') }} as grid
    inner join eligible_manifest_anchors as anchor
        on cast(grid.source_id as varchar) = anchor.anchor_source_id
       and cast(grid.selected_dag_run_id as varchar) = anchor.anchor_dag_run_id
    where cast(grid.published_at as timestamp(6))
          >= timestamp '{{ weather_w2_repair_start_at() }}'
      and cast(grid.published_at as timestamp(6))
          <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
),

ranked_grid_candidate_keys as (
    select
        grid_candidates.*,
        row_number() over (
            partition by nx, ny, forecast_at, category
            order by
                issued_at desc,
                collected_at desc,
                raw_object_key desc,
                request_id desc,
                dag_run_id desc,
                source_grid_place_id desc,
                nx desc,
                ny desc
        ) as product_row_num
    from grid_candidates
),

expected_keys as (
    select
        bridge.admin_dong_code,
        winner.forecast_at,
        winner.category
    from ranked_grid_candidate_keys as winner
    inner join active_bridge as bridge
        on winner.nx = bridge.nx
       and winner.ny = bridge.ny
    inner join canonical
        on bridge.admin_dong_code = canonical.admin_dong_code
    where winner.product_row_num = 1
),

actual_window as (
    select
        cast(product_row_id as varchar) as product_row_id,
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(forecast_at as timestamp(6)) as forecast_at,
        cast(category as varchar) as category
    from {{ ref('gold_weather_forecast_by_admin_dong') }}
    where cast(published_at as timestamp(6))
          >= timestamp '{{ weather_w2_repair_start_at() }}'
      and cast(published_at as timestamp(6))
          <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
)

select
    actual.product_row_id,
    cast('unexpected_window_gold_row' as varchar) as failure_reason
from actual_window as actual
left join expected_keys as expected
    on actual.admin_dong_code = expected.admin_dong_code
   and actual.forecast_at = expected.forecast_at
   and actual.category = expected.category
where expected.admin_dong_code is null
{% else %}
select cast(null as varchar) as product_row_id,
       cast(null as varchar) as failure_reason
where false
{% endif %}
