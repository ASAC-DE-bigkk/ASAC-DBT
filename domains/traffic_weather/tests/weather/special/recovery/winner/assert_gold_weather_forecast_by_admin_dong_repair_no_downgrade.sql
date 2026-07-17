-- depends_on: {{ ref('gold_weather_forecast_by_admin_dong') }}
-- depends_on: {{ ref('bridge_weather_admin_dong_grid') }}
-- depends_on: {{ ref('asac_axes', 'dim_admin_dong') }}
-- depends_on: {{ ref('silver_kma_vilage_fcst_grid') }}

{% set canonical_contract = weather_w2_canonical_contract() %}
{% set repair_mode = weather_w2_is_repair() %}
{% set winner_bucket_count = var('weather_w2_winner_bucket_count', 8) | int %}
{% set winner_bucket_index = var('weather_w2_winner_bucket_index', 0) | int %}
{% set gold_relation = ref('gold_weather_forecast_by_admin_dong') %}
{% set bridge_relation = ref('bridge_weather_admin_dong_grid') %}
{% set canonical_relation = ref('asac_axes', 'dim_admin_dong') %}
{% set grid_relation = ref('silver_kma_vilage_fcst_grid') %}

{% if winner_bucket_count < 1
    or winner_bucket_index < 0
    or winner_bucket_index >= winner_bucket_count %}
    {{ exceptions.raise_compiler_error(
        'Weather W2 winner bucket은 0 이상 count 미만이어야 합니다.'
    ) }}
{% endif %}

{% if repair_mode %}
with eligible_manifest_anchors as (
    {{ weather_w2_latest_publishable_anchors_sql() }}
),

active_bridge as (
    select
        cast(source_admin_code as varchar) as admin_dong_code,
        cast(nx as integer) as nx,
        cast(ny as integer) as ny
    from {{ bridge_relation }}
    where cast(bridge_version as varchar) = '{{ weather_w2_bridge_version() }}'
),

canonical as (
    select cast(admin_dong_code as varchar) as admin_dong_code
    from {{ canonical_relation }}
    where cast(revision_date as date) = date '{{ canonical_contract['revision_date'] }}'
),

grid_candidates as (
    select
        cast(grid.nx as integer) as nx,
        cast(grid.ny as integer) as ny,
        cast(grid.source_grid_place_id as varchar) as source_grid_place_id,
        cast(grid.issued_at as timestamp(6)) as issued_at,
        cast(grid.forecast_at as timestamp(6)) as forecast_at,
        cast(grid.category as varchar) as category,
        cast(grid.collected_at as timestamp(6)) as collected_at,
        cast(grid.selected_dag_run_id as varchar) as dag_run_id,
        cast(grid.raw_object_key as varchar) as raw_object_key,
        cast(grid.request_id as varchar) as request_id
    from {{ grid_relation }} as grid
    inner join eligible_manifest_anchors as anchor
        on cast(grid.source_id as varchar) = anchor.anchor_source_id
       and cast(grid.selected_dag_run_id as varchar) = anchor.anchor_dag_run_id
    where cast(grid.published_at as timestamp(6))
          >= timestamp '{{ weather_w2_repair_start_at() }}'
      and cast(grid.published_at as timestamp(6))
          <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
),

joined_candidates as (
    select
        bridge.admin_dong_code,
        grid.forecast_at,
        grid.category,
        grid.issued_at,
        grid.collected_at,
        grid.raw_object_key,
        grid.request_id,
        grid.dag_run_id,
        grid.source_grid_place_id,
        grid.nx,
        grid.ny
    from grid_candidates as grid
    inner join active_bridge as bridge
        on grid.nx = bridge.nx
       and grid.ny = bridge.ny
    inner join canonical
        on bridge.admin_dong_code = canonical.admin_dong_code
),

bucketed_candidates as (
    select *
    from joined_candidates
    where {{ weather_w2_canonical_grain_bucket(
        'joined_candidates', winner_bucket_count
    ) }} = {{ winner_bucket_index }}
),

winning_candidates as (
    select
        admin_dong_code,
        forecast_at,
        category,
        max_by(
            cast(row(
                issued_at,
                collected_at,
                raw_object_key,
                request_id,
                dag_run_id,
                source_grid_place_id,
                nx,
                ny
            ) as row(
                issued_at timestamp(6),
                collected_at timestamp(6),
                raw_object_key varchar,
                request_id varchar,
                dag_run_id varchar,
                source_grid_place_id varchar,
                nx integer,
                ny integer
            )),
            {{ weather_w2_grid_winner_order_key('bucketed_candidates') }}
        ) as winner
    from bucketed_candidates
    group by admin_dong_code, forecast_at, category
),

expected as (
    select
        admin_dong_code,
        forecast_at,
        category,
        winner.issued_at,
        winner.collected_at,
        winner.raw_object_key,
        winner.request_id,
        winner.dag_run_id,
        winner.source_grid_place_id,
        winner.nx,
        winner.ny
    from winning_candidates
),

actual as (
    select
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(forecast_at as timestamp(6)) as forecast_at,
        cast(category as varchar) as category,
        cast(issued_at as timestamp(6)) as issued_at,
        cast(collected_at as timestamp(6)) as collected_at,
        cast(raw_object_key as varchar) as raw_object_key,
        cast(request_id as varchar) as request_id,
        cast(dag_run_id as varchar) as dag_run_id,
        cast(source_grid_place_id as varchar) as source_grid_place_id,
        cast(nx as integer) as nx,
        cast(ny as integer) as ny,
        cast(published_at as timestamp(6)) as published_at,
        cast(source_id as varchar) as source_id
    from {{ gold_relation }}
)

select
    expected.admin_dong_code,
    expected.forecast_at,
    expected.category,
    cast('missing_older_or_ineligible_newer_target' as varchar) as failure_reason
from expected
left join actual
    on expected.admin_dong_code = actual.admin_dong_code
   and expected.forecast_at = actual.forecast_at
   and expected.category = actual.category
where actual.admin_dong_code is null
   or not {{ weather_w2_gold_winner_is_not_older('actual', 'expected') }}
   or (
       {{ weather_w2_gold_winner_is_not_older('actual', 'expected') }}
       and not {{ weather_w2_gold_winner_is_not_older('expected', 'actual') }}
       and actual.published_at >= timestamp '{{ weather_w2_repair_start_at() }}'
       and actual.published_at <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
       and not exists (
           select 1
           from eligible_manifest_anchors as anchor
           where anchor.anchor_source_id = actual.source_id
             and anchor.anchor_dag_run_id = actual.dag_run_id
       )
   )
{% else %}
select cast(null as varchar) as admin_dong_code,
       cast(null as timestamp(6)) as forecast_at,
       cast(null as varchar) as category,
       cast(null as varchar) as failure_reason
where false
{% endif %}
