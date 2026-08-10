-- depends_on: {{ ref('gold_weather_forecast_by_admin_dong') }}

{% set canonical_contract = weather_w2_canonical_contract() %}
{% set repair_mode = weather_w2_is_repair() %}
{% set snapshot_dag_run_id = var('weather_snapshot_dag_run_id', none) %}
{% if not repair_mode %}
    {% if snapshot_dag_run_id is none and not execute %}
        {% set snapshot_dag_run_id = 'parse-only' %}
    {% elif snapshot_dag_run_id is not string
          or snapshot_dag_run_id | length == 0 %}
        {{ exceptions.raise_compiler_error(
            'Weather W2 routine latest-record contract requires weather_snapshot_dag_run_id.'
        ) }}
    {% endif %}
{% endif %}

with active_bridge as (
    select
        cast(source_admin_code as varchar) as admin_dong_code,
        cast(bridge_version as varchar) as bridge_version,
        cast(nx as integer) as nx,
        cast(ny as integer) as ny
    from {{ ref('bridge_weather_admin_dong_grid') }}
    where cast(bridge_version as varchar) = 'weather_admin_dong_grid_bridge_v1'
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
),

{% if weather_w2_is_repair() %}
eligible_manifest_anchors as (
    {{ weather_w2_latest_publishable_anchors_sql() }}
),
{% else %}
latest_manifest_state as (
    {{ latest_manifest_run_state(
        'weather_bronze',
        'collection_run_manifest',
        'kma_vilage_fcst'
    ) }}
),

eligible_manifest_anchors as (
    select
        cast(source_id as varchar) as anchor_source_id,
        cast(dag_run_id as varchar) as anchor_dag_run_id
    from latest_manifest_state
    where manifest_status = 'SUCCESS'
      and is_publishable
),
{% endif %}

{% if not repair_mode %}
snapshot_grid_keys as (
    select distinct
        cast(grid.nx as integer) as nx,
        cast(grid.ny as integer) as ny,
        cast(grid.forecast_at as timestamp(6)) as forecast_at,
        cast(grid.category as varchar) as category
    from {{ ref('silver_kma_vilage_fcst_grid') }} as grid
    inner join eligible_manifest_anchors as anchor
        on cast(grid.source_id as varchar) = anchor.anchor_source_id
       and cast(grid.selected_dag_run_id as varchar) = anchor.anchor_dag_run_id
    where cast(grid.selected_dag_run_id as varchar)
          = '{{ snapshot_dag_run_id | replace("'", "''") }}'
),

affected_product_keys as (
    select distinct
        bridge.admin_dong_code,
        snapshot.forecast_at,
        snapshot.category
    from snapshot_grid_keys as snapshot
    inner join active_bridge as bridge
        on snapshot.nx = bridge.nx
       and snapshot.ny = bridge.ny
),
{% endif %}

joined_candidates as (
    select
        bridge.admin_dong_code,
        canonical.admin_dong,
        canonical.gu_code,
        canonical.gu,
        canonical.admin_dong_revision_date,
        cast(grid.forecast_at as timestamp(6)) as forecast_at,
        cast(grid.category as varchar) as category,
        bridge.bridge_version,
        cast(grid.issued_at as timestamp(6)) as issued_at,
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
        cast(grid.raw_object_key as varchar) as raw_object_key,
        cast(grid.request_id as varchar) as request_id,
        cast(grid.selected_dag_run_id as varchar) as dag_run_id,
        cast(grid.source_grid_place_id as varchar) as source_grid_place_id,
        cast(grid.nx as integer) as nx,
        cast(grid.ny as integer) as ny
    from {{ ref('silver_kma_vilage_fcst_grid') }} as grid
    inner join active_bridge as bridge
        on cast(grid.nx as integer) = bridge.nx
       and cast(grid.ny as integer) = bridge.ny
    inner join canonical
        on bridge.admin_dong_code = canonical.admin_dong_code
    inner join eligible_manifest_anchors as anchor
        on cast(grid.source_id as varchar) = anchor.anchor_source_id
       and cast(grid.selected_dag_run_id as varchar) = anchor.anchor_dag_run_id
    {% if not repair_mode %}
    inner join affected_product_keys as affected
        on bridge.admin_dong_code = affected.admin_dong_code
       and cast(grid.forecast_at as timestamp(6)) = affected.forecast_at
       and cast(grid.category as varchar) = affected.category
    {% else %}
    where cast(grid.published_at as timestamp(6))
          >= timestamp '{{ weather_w2_repair_start_at() }}'
      and cast(grid.published_at as timestamp(6))
          <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
    {% endif %}
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

expected as (
    select
        winner.admin_dong_code,
        winner.forecast_at,
        winner.category,
        winner.bridge_version,
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
        gold.admin_dong_code,
        gold.forecast_at,
        gold.category,
        gold.bridge_version,
        gold.issued_at,
        gold.collected_at,
        gold.published_at,
        gold.fcst_value_raw,
        gold.fcst_value_num,
        gold.value_representation,
        gold.value_num,
        gold.value_lower_bound,
        gold.value_upper_bound,
        gold.qualitative_code,
        gold.forecast_lead_hours,
        gold.source_id,
        gold.raw_object_key,
        gold.request_id,
        gold.dag_run_id,
        gold.source_grid_place_id,
        gold.nx,
        gold.ny
    from {{ ref('gold_weather_forecast_by_admin_dong') }} as gold
    {% if not repair_mode %}
    inner join affected_product_keys as affected
        on gold.admin_dong_code = affected.admin_dong_code
       and gold.forecast_at = affected.forecast_at
       and gold.category = affected.category
    {% endif %}
)

select
    expected.admin_dong_code,
    expected.forecast_at,
    expected.category,
    expected.issued_at as expected_issued_at,
    actual.issued_at as actual_issued_at,
    expected.dag_run_id as expected_dag_run_id,
    actual.dag_run_id as actual_dag_run_id,
    expected.raw_object_key as expected_raw_object_key,
    actual.raw_object_key as actual_raw_object_key,
    expected.request_id as expected_request_id,
    actual.request_id as actual_request_id
from expected
left join actual
    on expected.admin_dong_code = actual.admin_dong_code
   and expected.forecast_at = actual.forecast_at
   and expected.category = actual.category
where actual.admin_dong_code is null
{% if repair_mode %}
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
   or (
       {{ weather_w2_gold_winner_is_not_older('expected', 'actual') }}
       and (
           actual.bridge_version is distinct from expected.bridge_version
           or actual.nx is distinct from expected.nx
           or actual.ny is distinct from expected.ny
           or actual.source_grid_place_id is distinct from expected.source_grid_place_id
           or actual.issued_at is distinct from expected.issued_at
           or actual.collected_at is distinct from expected.collected_at
           or actual.published_at is distinct from expected.published_at
           or actual.fcst_value_raw is distinct from expected.fcst_value_raw
           or actual.fcst_value_num is distinct from expected.fcst_value_num
           or actual.value_representation is distinct from expected.value_representation
           or actual.value_num is distinct from expected.value_num
           or actual.value_lower_bound is distinct from expected.value_lower_bound
           or actual.value_upper_bound is distinct from expected.value_upper_bound
           or actual.qualitative_code is distinct from expected.qualitative_code
           or actual.forecast_lead_hours is distinct from expected.forecast_lead_hours
           or actual.source_id is distinct from expected.source_id
           or actual.dag_run_id is distinct from expected.dag_run_id
           or actual.raw_object_key is distinct from expected.raw_object_key
           or actual.request_id is distinct from expected.request_id
       )
   )
{% else %}
   or actual.bridge_version is distinct from expected.bridge_version
   or actual.nx is distinct from expected.nx
   or actual.ny is distinct from expected.ny
   or actual.source_grid_place_id is distinct from expected.source_grid_place_id
   or actual.issued_at is distinct from expected.issued_at
   or actual.collected_at is distinct from expected.collected_at
   or actual.published_at is distinct from expected.published_at
   or actual.fcst_value_raw is distinct from expected.fcst_value_raw
   or actual.fcst_value_num is distinct from expected.fcst_value_num
   or actual.value_representation is distinct from expected.value_representation
   or actual.value_num is distinct from expected.value_num
   or actual.value_lower_bound is distinct from expected.value_lower_bound
   or actual.value_upper_bound is distinct from expected.value_upper_bound
   or actual.qualitative_code is distinct from expected.qualitative_code
   or actual.forecast_lead_hours is distinct from expected.forecast_lead_hours
   or actual.source_id is distinct from expected.source_id
   or actual.raw_object_key is distinct from expected.raw_object_key
   or actual.request_id is distinct from expected.request_id
   or actual.dag_run_id is distinct from expected.dag_run_id
{% endif %}
