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
    select cast(admin_dong_code as varchar) as admin_dong_code
    from {{ ref('asac_axes', 'dim_admin_dong') }}
    where cast(revision_date as date) = date '{{ canonical_contract['revision_date'] }}'
),

repair_grid_candidate_keys as (
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

ranked_repair_grid_candidate_keys as (
    select
        repair_grid_candidate_keys.*,
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
    from repair_grid_candidate_keys
),

repair_product_keys as (
    select
        bridge.admin_dong_code,
        winner.forecast_at,
        winner.category,
        winner.issued_at,
        winner.collected_at,
        winner.raw_object_key,
        winner.request_id,
        winner.dag_run_id,
        winner.source_grid_place_id,
        winner.nx,
        winner.ny
    from ranked_repair_grid_candidate_keys as winner
    inner join active_bridge as bridge
        on winner.nx = bridge.nx
       and winner.ny = bridge.ny
    inner join canonical
        on bridge.admin_dong_code = canonical.admin_dong_code
    where winner.product_row_num = 1
),

actual_repair_products as (
    select
        cast(actual.product_row_id as varchar) as product_row_id,
        cast(actual.admin_dong_code as varchar) as admin_dong_code,
        cast(actual.forecast_at as timestamp(6)) as forecast_at,
        cast(actual.category as varchar) as category,
        cast(actual.bridge_version as varchar) as bridge_version,
        cast(actual.nx as integer) as nx,
        cast(actual.ny as integer) as ny,
        cast(actual.source_grid_place_id as varchar) as source_grid_place_id,
        cast(actual.issued_at as timestamp(6)) as issued_at,
        cast(actual.collected_at as timestamp(6)) as collected_at,
        cast(actual.published_at as timestamp(6)) as published_at,
        cast(actual.fcst_value_raw as varchar) as fcst_value_raw,
        cast(actual.fcst_value_num as double) as fcst_value_num,
        cast(actual.value_representation as varchar) as value_representation,
        cast(actual.value_num as double) as value_num,
        cast(actual.value_lower_bound as double) as value_lower_bound,
        cast(actual.value_upper_bound as double) as value_upper_bound,
        cast(actual.qualitative_code as varchar) as qualitative_code,
        cast(actual.forecast_lead_hours as bigint) as forecast_lead_hours,
        cast(actual.source_id as varchar) as source_id,
        cast(actual.dag_run_id as varchar) as dag_run_id,
        cast(actual.raw_object_key as varchar) as raw_object_key,
        cast(actual.request_id as varchar) as request_id
    from {{ ref('gold_weather_forecast_by_admin_dong') }} as actual
    inner join repair_product_keys as expected
        on cast(actual.admin_dong_code as varchar) = expected.admin_dong_code
       and cast(actual.forecast_at as timestamp(6)) = expected.forecast_at
       and cast(actual.category as varchar) = expected.category
    where {{ weather_w2_gold_winner_is_not_older('actual', 'expected') }}
),

lineage_backed_products as (
    select distinct actual.product_row_id
    from actual_repair_products as actual
    inner join active_bridge as bridge
        on bridge.admin_dong_code = actual.admin_dong_code
       and bridge.bridge_version is not distinct from actual.bridge_version
       and bridge.nx is not distinct from actual.nx
       and bridge.ny is not distinct from actual.ny
    inner join canonical
        on bridge.admin_dong_code = canonical.admin_dong_code
    inner join {{ ref('silver_kma_vilage_fcst_grid') }} as grid
        on cast(grid.nx as integer) is not distinct from actual.nx
       and cast(grid.ny as integer) is not distinct from actual.ny
       and cast(grid.source_grid_place_id as varchar) is not distinct from actual.source_grid_place_id
       and cast(grid.forecast_at as timestamp(6)) is not distinct from actual.forecast_at
       and cast(grid.category as varchar) is not distinct from actual.category
       and cast(grid.issued_at as timestamp(6)) is not distinct from actual.issued_at
       and cast(grid.collected_at as timestamp(6)) is not distinct from actual.collected_at
       and cast(grid.published_at as timestamp(6)) is not distinct from actual.published_at
       and cast(grid.fcst_value_raw as varchar) is not distinct from actual.fcst_value_raw
       and cast(grid.fcst_value_num as double) is not distinct from actual.fcst_value_num
       and cast(grid.value_representation as varchar) is not distinct from actual.value_representation
       and cast(grid.value_num as double) is not distinct from actual.value_num
       and cast(grid.value_lower_bound as double) is not distinct from actual.value_lower_bound
       and cast(grid.value_upper_bound as double) is not distinct from actual.value_upper_bound
       and cast(grid.qualitative_code as varchar) is not distinct from actual.qualitative_code
       and cast(grid.forecast_lead_hours as bigint) is not distinct from actual.forecast_lead_hours
       and cast(grid.source_id as varchar) is not distinct from actual.source_id
       and cast(grid.selected_dag_run_id as varchar) is not distinct from actual.dag_run_id
       and cast(grid.raw_object_key as varchar) is not distinct from actual.raw_object_key
       and cast(grid.request_id as varchar) is not distinct from actual.request_id
)

select
    actual.product_row_id,
    cast('forecast_lineage_not_backed_by_one_grid_row' as varchar) as failure_reason
from actual_repair_products as actual
left join lineage_backed_products as backed
    on actual.product_row_id = backed.product_row_id
where backed.product_row_id is null
{% else %}
select cast(null as varchar) as product_row_id,
       cast(null as varchar) as failure_reason
where false
{% endif %}
