-- depends_on: {{ ref('weather_w2_observation_recovery_stage') }}
-- depends_on: {{ ref('bridge_weather_admin_dong_grid') }}
-- depends_on: {{ ref('silver_kma_vilage_fcst_grid') }}
-- depends_on: {{ ref('asac_axes', 'dim_admin_dong') }}

{% set repair_mode = weather_w2_is_repair() %}
{% if repair_mode %}
{% set checkpoint_id = weather_w2_recovery_checkpoint_id() %}
{% set target_admin_dong_code = weather_w2_recovery_target_admin_dong_code() %}
{% set canonical_contract = weather_w2_canonical_contract() %}

with eligible_manifest_anchors as (
    {{ weather_w2_latest_publishable_anchors_sql() }}
),

active_bridge as (
    select
        cast(source_admin_code as varchar) as admin_dong_code,
        cast(bridge_version as varchar) as bridge_version,
        cast(nx as integer) as nx,
        cast(ny as integer) as ny
    from {{ weather_w2_bridge_at_snapshot() }}
    where cast(source_admin_code as varchar) = '{{ target_admin_dong_code }}'
      and cast(nx as integer) = 61
      and cast(ny as integer) = 127
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
        grid.*
    from grid_candidates as grid
    inner join active_bridge as bridge
        on grid.nx = bridge.nx
       and grid.ny = bridge.ny
    inner join canonical
        on bridge.admin_dong_code = canonical.admin_dong_code
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
),

expected_rows as (
    select
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
),

expected as (
    select
        expected_rows.*,
        {{ weather_w2_gold_candidate_row('expected_rows') }} as expected_payload
    from expected_rows
),

actual as (
    select *
    from {{ ref('weather_w2_observation_recovery_stage') }}
    where checkpoint_id = '{{ checkpoint_id }}'
      and window_start_at = timestamp '{{ weather_w2_repair_start_at() }}'
      and window_cutoff_at = timestamp '{{ weather_w2_publishable_cutoff_at() }}'
),

invalid_actual as (
    select
        product_row_id,
        case
            when checkpoint_id != '{{ checkpoint_id }}'
                then 'wrong_checkpoint_id'
            when admin_dong_code != '{{ target_admin_dong_code }}'
                then 'wrong_target_admin_dong'
            when nx != 61 or ny != 127
                then 'wrong_target_grid'
            else 'null_grain_or_lineage'
        end as failure_reason
    from actual
    where checkpoint_id != '{{ checkpoint_id }}'
       or admin_dong_code != '{{ target_admin_dong_code }}'
       or nx != 61
       or ny != 127
       or product_row_id is null
       or admin_dong_code is null
       or forecast_at is null
       or category is null
       or issued_at is null
       or collected_at is null
       or published_at is null
       or source_id is null
       or dag_run_id is null
       or raw_object_key is null
       or request_id is null
),

duplicate_actual as (
    select
        min(product_row_id) as product_row_id,
        cast('duplicate_stage_grain' as varchar) as failure_reason
    from actual
    group by checkpoint_id, admin_dong_code, forecast_at, category
    having count(*) > 1
),

missing_or_different as (
    select
        expected.product_row_id,
        case
            when actual.product_row_id is null
                then 'missing_expected_stage_row'
            else 'stage_payload_differs_from_pinned_winner'
        end as failure_reason
    from expected
    left join actual
        on expected.admin_dong_code = actual.admin_dong_code
       and expected.forecast_at = actual.forecast_at
       and expected.category = actual.category
    where actual.product_row_id is null
       or {{ weather_w2_gold_candidate_row('actual') }}
          is distinct from expected.expected_payload
),

unexpected_actual as (
    select
        actual.product_row_id,
        cast('unexpected_stage_window_row' as varchar) as failure_reason
    from actual
    left join expected
        on actual.admin_dong_code = expected.admin_dong_code
       and actual.forecast_at = expected.forecast_at
       and actual.category = expected.category
    where expected.product_row_id is null
)

select * from invalid_actual
union all
select * from duplicate_actual
union all
select * from missing_or_different
union all
select * from unexpected_actual
{% else %}
select
    cast(null as varchar) as product_row_id,
    cast(null as varchar) as failure_reason
where false
{% endif %}
