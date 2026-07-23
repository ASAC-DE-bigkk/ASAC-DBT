-- W2 public Gold: latest forecast at product grain stamped by an approved canonical revision.
-- depends_on: {{ ref('bridge_weather_admin_dong_grid') }}
-- depends_on: {{ ref('asac_axes', 'seoul_admin_dong_crosswalk') }}
-- depends_on: {{ source('axes_bronze', 'admin_dong_master') }}
-- depends_on: {{ ref('silver_kma_vilage_fcst_grid') }}
{{ config(
    materialized='incremental',
    incremental_strategy='weather_w2_reconcile',
    unique_key=['admin_dong_code', 'forecast_at', 'category'],
    on_schema_change='fail',
    views_enabled=false,
    on_table_exists='drop',
    full_refresh=false,
) }}

{{ weather_w2_assert_gold_dev_target() }}
{% set canonical_contract = weather_w2_canonical_contract() %}
{{ weather_w2_gold_initial_build_guard() }}
{{ weather_w2_assert_repair_evidence() }}
{{ weather_w2_assert_gold_source_contract() }}

with canonical as (
    select
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(admin_dong as varchar) as admin_dong,
        cast(gu_code as varchar) as gu_code,
        cast(gu as varchar) as gu,
        cast(canonical.revision_date as date) as admin_dong_revision_date
    from {{ asac_axes.pinned_dim_admin_dong() }} as canonical
    where cast(canonical.revision_date as date) = date '{{ canonical_contract['revision_date'] }}'
),

active_bridge as (
    select
        cast(source_admin_code as varchar) as source_admin_code,
        cast(bridge_version as varchar) as bridge_version,
        cast(nx as integer) as nx,
        cast(ny as integer) as ny
    from {{ ref('bridge_weather_admin_dong_grid') }}
    where cast(bridge_version as varchar) = 'weather_admin_dong_grid_bridge_v1'
),

canonical_summary as (
    select
        count(*) as canonical_row_count,
        count(distinct admin_dong_code) as canonical_code_count,
        count(distinct admin_dong_revision_date) as canonical_revision_count,
        min(admin_dong_revision_date) as min_canonical_revision,
        max(admin_dong_revision_date) as max_canonical_revision,
        count_if(
            admin_dong_code is null
            or admin_dong is null
            or gu_code is null
            or gu is null
            or admin_dong_revision_date is null
        ) as canonical_null_count
    from canonical
),

active_bridge_summary as (
    select
        count(*) as bridge_row_count,
        count(distinct source_admin_code) as bridge_admin_code_count,
        count_if(
            source_admin_code is null
            or bridge_version is null
            or nx is null
            or ny is null
        ) as bridge_null_count
    from active_bridge
),

mapped_canonical_summary as (
    select
        count(*) as mapped_canonical_row_count,
        count(distinct active_bridge.source_admin_code) as mapped_canonical_code_count
    from active_bridge
    inner join canonical
        on active_bridge.source_admin_code = canonical.admin_dong_code
),

validated_canonical_contract as (
    select
        (
            canonical_summary.canonical_row_count = {{ canonical_contract['canonical_count'] }}
            and canonical_summary.canonical_code_count = {{ canonical_contract['canonical_count'] }}
            and canonical_summary.canonical_revision_count = 1
            and canonical_summary.min_canonical_revision = date '{{ canonical_contract['revision_date'] }}'
            and canonical_summary.max_canonical_revision = date '{{ canonical_contract['revision_date'] }}'
            and canonical_summary.canonical_null_count = 0
            and active_bridge_summary.bridge_row_count = {{ canonical_contract['bridge_count'] }}
            and active_bridge_summary.bridge_admin_code_count = {{ canonical_contract['bridge_count'] }}
            and active_bridge_summary.bridge_null_count = 0
            and mapped_canonical_summary.mapped_canonical_row_count = {{ canonical_contract['mapped_canonical_count'] }}
            and mapped_canonical_summary.mapped_canonical_code_count = {{ canonical_contract['mapped_canonical_count'] }}
        ) as canonical_contract_guard
    from canonical_summary
    cross join active_bridge_summary
    cross join mapped_canonical_summary
),

canonical_contract_failure_rows as (
    select
        cast(
            if(
                canonical_contract_guard,
                cast(null as integer),
                1 / cast(0 as integer)
            ) as varchar
        ) as product_row_id,
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
    from validated_canonical_contract
    where not canonical_contract_guard
),

{% if weather_w2_is_repair() %}
eligible_manifest_anchors as (
    {{ weather_w2_latest_publishable_anchors_sql() }}
),
{% endif %}

grid_candidates as (
    select
        cast(nx as integer) as nx,
        cast(ny as integer) as ny,
        cast(source_grid_place_id as varchar) as source_grid_place_id,
        cast(issued_at as timestamp(6)) as issued_at,
        cast(forecast_at as timestamp(6)) as forecast_at,
        cast(category as varchar) as category,
        cast(collected_at as timestamp(6)) as collected_at,
        cast(published_at as timestamp(6)) as published_at,
        cast(fcst_value_raw as varchar) as fcst_value_raw,
        cast(fcst_value_num as double) as fcst_value_num,
        cast(value_representation as varchar) as value_representation,
        cast(value_num as double) as value_num,
        cast(value_lower_bound as double) as value_lower_bound,
        cast(value_upper_bound as double) as value_upper_bound,
        cast(qualitative_code as varchar) as qualitative_code,
        cast(forecast_lead_hours as bigint) as forecast_lead_hours,
        cast(source_id as varchar) as source_id,
        cast(selected_dag_run_id as varchar) as dag_run_id,
        cast(raw_object_key as varchar) as raw_object_key,
        cast(request_id as varchar) as request_id
    from {{ ref('silver_kma_vilage_fcst_grid') }} as grid
    {% if weather_w2_is_repair() %}
    inner join eligible_manifest_anchors as anchor
        on cast(grid.source_id as varchar) = anchor.anchor_source_id
       and cast(grid.selected_dag_run_id as varchar) = anchor.anchor_dag_run_id
    where grid.published_at >= timestamp '{{ weather_w2_repair_start_at() }}'
      and grid.published_at <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
    {% elif is_incremental() %}
    where collected_at >= (
        select
            coalesce(max(collected_at), timestamp '1970-01-01 00:00:00')
            - interval '{{ weather_w1_lookback_minutes() }}' minute
        from {{ this }}
    )
    {% endif %}
),

joined_candidates as (
    select
        canonical.admin_dong_code,
        canonical.admin_dong,
        canonical.gu_code,
        canonical.gu,
        canonical.admin_dong_revision_date,
        active_bridge.bridge_version,
        grid_candidates.nx,
        grid_candidates.ny,
        grid_candidates.source_grid_place_id,
        grid_candidates.issued_at,
        grid_candidates.forecast_at,
        grid_candidates.category,
        grid_candidates.collected_at,
        grid_candidates.published_at,
        grid_candidates.fcst_value_raw,
        grid_candidates.fcst_value_num,
        grid_candidates.value_representation,
        grid_candidates.value_num,
        grid_candidates.value_lower_bound,
        grid_candidates.value_upper_bound,
        grid_candidates.qualitative_code,
        grid_candidates.forecast_lead_hours,
        grid_candidates.source_id,
        grid_candidates.dag_run_id,
        grid_candidates.raw_object_key,
        grid_candidates.request_id
    from grid_candidates
    inner join active_bridge
        on grid_candidates.nx = active_bridge.nx
       and grid_candidates.ny = active_bridge.ny
    inner join canonical
        on active_bridge.source_admin_code = canonical.admin_dong_code
    cross join validated_canonical_contract
    where validated_canonical_contract.canonical_contract_guard
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
        concat(winner.admin_dong_code, '|', to_iso8601(cast(winner.forecast_at as timestamp(6))), '|', winner.category) as product_row_id,
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
)

select
    product_row_id,
    admin_dong_code,
    forecast_at,
    category,
    admin_dong,
    gu_code,
    gu,
    admin_dong_revision_date,
    bridge_version,
    nx,
    ny,
    source_grid_place_id,
    issued_at,
    collected_at,
    published_at,
    fcst_value_raw,
    fcst_value_num,
    value_representation,
    value_num,
    value_lower_bound,
    value_upper_bound,
    qualitative_code,
    forecast_lead_hours,
    source_id,
    dag_run_id,
    raw_object_key,
    request_id
from expected_rows
union all
select
    product_row_id,
    admin_dong_code,
    forecast_at,
    category,
    admin_dong,
    gu_code,
    gu,
    admin_dong_revision_date,
    bridge_version,
    nx,
    ny,
    source_grid_place_id,
    issued_at,
    collected_at,
    published_at,
    fcst_value_raw,
    fcst_value_num,
    value_representation,
    value_num,
    value_lower_bound,
    value_upper_bound,
    qualitative_code,
    forecast_lead_hours,
    source_id,
    dag_run_id,
    raw_object_key,
    request_id
from canonical_contract_failure_rows
