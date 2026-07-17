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
    from {{ ref('asac_axes', 'dim_admin_dong') }}
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
    from {{ ref('silver_kma_vilage_fcst_grid') }} as grid
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

boundary_expected as (
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
        winner.request_id,
        winner as expected_payload
    from winning_candidates
)

select
    expected.product_row_id,
    case
        when actual.product_row_id is null then 'missing_expected_gold_row'
        else 'gold_payload_differs_from_repair_winner'
    end as failure_reason
from boundary_expected as expected
left join {{ ref('gold_weather_forecast_by_admin_dong') }} as actual
    on expected.admin_dong_code = cast(actual.admin_dong_code as varchar)
   and expected.forecast_at = cast(actual.forecast_at as timestamp(6))
   and expected.category = cast(actual.category as varchar)
where actual.product_row_id is null
or (
    not (
        {{ weather_w2_gold_winner_is_not_older('actual', 'expected') }}
        and not {{ weather_w2_gold_winner_is_not_older('expected', 'actual') }}
        and (
            cast(actual.published_at as timestamp(6))
                < timestamp '{{ weather_w2_repair_start_at() }}'
            or cast(actual.published_at as timestamp(6))
                > timestamp '{{ weather_w2_publishable_cutoff_at() }}'
            or exists (
                select 1
                from eligible_manifest_anchors as anchor
                where anchor.anchor_source_id = cast(actual.source_id as varchar)
                  and anchor.anchor_dag_run_id = cast(actual.dag_run_id as varchar)
            )
        )
    )
    and {{ weather_w2_gold_candidate_row('actual') }}
        is distinct from expected.expected_payload
)
{% else %}
select cast(null as varchar) as failure_reason
where false
{% endif %}
