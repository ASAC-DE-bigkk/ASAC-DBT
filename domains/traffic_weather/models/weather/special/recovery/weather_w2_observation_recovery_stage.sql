-- Dev-only, checkpoint-scoped Gold staging for Yongsin-dong recovery.
-- depends_on: {{ ref('bridge_weather_admin_dong_grid') }}
-- depends_on: {{ ref('silver_kma_vilage_fcst_grid') }}
-- depends_on: {{ ref('asac_axes', 'dim_admin_dong') }}
{{ config(
    materialized='incremental',
    incremental_strategy='weather_w2_recovery_stage',
    unique_key=['checkpoint_id', 'admin_dong_code', 'forecast_at', 'category'],
    on_schema_change='fail',
    full_refresh=false,
) }}

{% set repair_mode = weather_w2_is_repair() %}
{% if execute and not repair_mode %}
  {{ exceptions.raise_compiler_error(
      'Weather W2 recovery stage can run only in staged bounded recovery mode.'
  ) }}
{% endif %}

{% if repair_mode %}
{{ weather_w2_assert_gold_target() }}
{{ weather_w2_assert_repair_evidence() }}

{% set checkpoint_id = weather_w2_recovery_checkpoint_id() %}
{% set target_admin_dong_code = weather_w2_recovery_target_admin_dong_code() %}
{% if target_admin_dong_code != '1123053600' %}
  {{ exceptions.raise_compiler_error(
      'Weather W2 recovery stage target must be Yongsin-dong.'
  ) }}
{% endif %}
{% set canonical_contract = weather_w2_canonical_contract() %}

with eligible_manifest_anchors as (
    {{ weather_w2_latest_publishable_anchors_sql() }}
),

active_bridge as (
    select
        cast(source_admin_code as varchar) as source_admin_code,
        cast(bridge_version as varchar) as bridge_version,
        cast(nx as integer) as nx,
        cast(ny as integer) as ny
    from {{ weather_w2_bridge_at_snapshot() }}
    where cast(source_admin_code as varchar) = '{{ target_admin_dong_code }}'
      and nx = 61
      and ny = 127
      and cast(bridge_version as varchar) = '{{ weather_w2_bridge_version() }}'
),

canonical as (
    select
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(admin_dong as varchar) as admin_dong,
        cast(gu_code as varchar) as gu_code,
        cast(gu as varchar) as gu,
        cast(revision_date as date) as admin_dong_revision_date
    from {{ asac_axes.pinned_dim_admin_dong() }}
    where cast(revision_date as date) = date '{{ canonical_contract['revision_date'] }}'
      and cast(admin_dong_code as varchar) = '{{ target_admin_dong_code }}'
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
        cast(grid.published_at as timestamp(6)) as published_at,
        cast(grid.fcst_value_raw as varchar) as fcst_value_raw,
        cast(grid.fcst_value_num as double) as fcst_value_num,
        cast(grid.value_representation as varchar) as value_representation,
        cast(grid.value_num as double) as value_num,
        cast(grid.value_lower_bound as double) as value_lower_bound,
        cast(grid.value_upper_bound as double) as value_upper_bound,
        cast(grid.qualitative_code as varchar) as qualitative_code,
        cast(grid.forecast_lead_hours as bigint) as forecast_lead_hours,
        cast(grid.source_id as varchar) as source_id,
        cast(grid.selected_dag_run_id as varchar) as dag_run_id,
        cast(grid.raw_object_key as varchar) as raw_object_key,
        cast(grid.request_id as varchar) as request_id
    from {{ weather_w2_silver_grid_at_snapshot() }} as grid
    inner join eligible_manifest_anchors as anchor
        on cast(grid.source_id as varchar) = anchor.anchor_source_id
       and cast(grid.selected_dag_run_id as varchar) = anchor.anchor_dag_run_id
    where cast(grid.published_at as timestamp(6))
          >= timestamp '{{ weather_w2_repair_start_at() }}'
      and cast(grid.published_at as timestamp(6))
          <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
      and cast(grid.nx as integer) = 61
      and cast(grid.ny as integer) = 127
),

joined_candidates as (
    select
        canonical.admin_dong_code,
        canonical.admin_dong,
        canonical.gu_code,
        canonical.gu,
        canonical.admin_dong_revision_date,
        bridge.bridge_version,
        grid.nx,
        grid.ny,
        grid.source_grid_place_id,
        grid.issued_at,
        grid.forecast_at,
        grid.category,
        grid.collected_at,
        grid.published_at,
        grid.fcst_value_raw,
        grid.fcst_value_num,
        grid.value_representation,
        grid.value_num,
        grid.value_lower_bound,
        grid.value_upper_bound,
        grid.qualitative_code,
        grid.forecast_lead_hours,
        grid.source_id,
        grid.dag_run_id,
        grid.raw_object_key,
        grid.request_id
    from grid_candidates as grid
    inner join active_bridge as bridge
        on grid.nx = bridge.nx
       and grid.ny = bridge.ny
    inner join canonical
        on bridge.source_admin_code = canonical.admin_dong_code
),

winning_candidates as (
    select
        admin_dong_code,
        forecast_at,
        category,
        max_by(
            {{ weather_w2_gold_candidate_row('joined_candidates') }},
            {{ weather_w2_grid_winner_order_key('joined_candidates') }}
        ) as winner
    from joined_candidates
    group by admin_dong_code, forecast_at, category
)

select
    cast('{{ checkpoint_id }}' as varchar) as checkpoint_id,
    timestamp '{{ weather_w2_repair_start_at() }}' as window_start_at,
    timestamp '{{ weather_w2_publishable_cutoff_at() }}' as window_cutoff_at,
    concat(
        winner.admin_dong_code,
        '|',
        to_iso8601(cast(winner.forecast_at as timestamp(6))),
        '|',
        winner.category
    ) as product_row_id,
    winner.admin_dong_code,
    winner.forecast_at,
    winner.category,
    winner.admin_dong,
    winner.gu_code,
    winner.gu,
    winner.admin_dong_revision_date,
    winner.bridge_version,
    winner.nx,
    winner.ny,
    winner.source_grid_place_id,
    winner.issued_at,
    winner.collected_at,
    winner.published_at,
    winner.fcst_value_raw,
    winner.fcst_value_num,
    winner.value_representation,
    winner.value_num,
    winner.value_lower_bound,
    winner.value_upper_bound,
    winner.qualitative_code,
    winner.forecast_lead_hours,
    winner.source_id,
    winner.dag_run_id,
    winner.raw_object_key,
    winner.request_id
from winning_candidates
{% else %}
select
    cast(null as varchar) as checkpoint_id,
    cast(null as timestamp(6)) as window_start_at,
    cast(null as timestamp(6)) as window_cutoff_at,
    cast(null as varchar) as product_row_id,
    cast(null as varchar) as admin_dong_code,
    cast(null as timestamp(6)) as forecast_at,
    cast(null as varchar) as category,
    cast(null as varchar) as admin_dong,
    cast(null as varchar) as gu_code,
    cast(null as varchar) as gu,
    cast(null as date) as admin_dong_revision_date,
    cast(null as varchar) as bridge_version,
    cast(null as integer) as nx,
    cast(null as integer) as ny,
    cast(null as varchar) as source_grid_place_id,
    cast(null as timestamp(6)) as issued_at,
    cast(null as timestamp(6)) as collected_at,
    cast(null as timestamp(6)) as published_at,
    cast(null as varchar) as fcst_value_raw,
    cast(null as double) as fcst_value_num,
    cast(null as varchar) as value_representation,
    cast(null as double) as value_num,
    cast(null as double) as value_lower_bound,
    cast(null as double) as value_upper_bound,
    cast(null as varchar) as qualitative_code,
    cast(null as bigint) as forecast_lead_hours,
    cast(null as varchar) as source_id,
    cast(null as varchar) as dag_run_id,
    cast(null as varchar) as raw_object_key,
    cast(null as varchar) as request_id
where false
{% endif %}
