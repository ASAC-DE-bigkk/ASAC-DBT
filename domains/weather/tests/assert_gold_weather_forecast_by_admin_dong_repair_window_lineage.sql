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

actual_lineage_runs as (
    -- An exact backing row must carry this same non-null source/run lineage.
    -- Restricting the Silver scan to those runs is semantically neutral and
    -- keeps the 6h repair validation below Trino's 2GB query cap.
    select distinct source_id, dag_run_id
    from actual_repair_products
),

actual_lineage_payloads as (
    select
        actual.product_row_id,
        json_format(cast(row(
            actual.admin_dong_code,
            actual.bridge_version,
            actual.nx,
            actual.ny,
            actual.source_grid_place_id,
            actual.forecast_at,
            actual.category,
            actual.issued_at,
            actual.collected_at,
            actual.published_at,
            actual.fcst_value_raw,
            actual.fcst_value_num,
            actual.value_representation,
            actual.value_num,
            actual.value_lower_bound,
            actual.value_upper_bound,
            actual.qualitative_code,
            actual.forecast_lead_hours,
            actual.source_id,
            actual.dag_run_id,
            actual.raw_object_key,
            actual.request_id
        ) as json)) as lineage_payload
    from actual_repair_products as actual
),

lineage_grid_payloads as (
    select distinct
        json_format(cast(row(
            bridge.admin_dong_code,
            bridge.bridge_version,
            cast(grid.nx as integer),
            cast(grid.ny as integer),
            cast(grid.source_grid_place_id as varchar),
            cast(grid.forecast_at as timestamp(6)),
            cast(grid.category as varchar),
            cast(grid.issued_at as timestamp(6)),
            cast(grid.collected_at as timestamp(6)),
            cast(grid.published_at as timestamp(6)),
            cast(grid.fcst_value_raw as varchar),
            cast(grid.fcst_value_num as double),
            cast(grid.value_representation as varchar),
            cast(grid.value_num as double),
            cast(grid.value_lower_bound as double),
            cast(grid.value_upper_bound as double),
            cast(grid.qualitative_code as varchar),
            cast(grid.forecast_lead_hours as bigint),
            cast(grid.source_id as varchar),
            cast(grid.selected_dag_run_id as varchar),
            cast(grid.raw_object_key as varchar),
            cast(grid.request_id as varchar)
        ) as json)) as lineage_payload
    from {{ ref('silver_kma_vilage_fcst_grid') }} as grid
    inner join actual_lineage_runs as run
        on cast(grid.source_id as varchar) = run.source_id
       and cast(grid.selected_dag_run_id as varchar) = run.dag_run_id
    inner join active_bridge as bridge
        on cast(grid.nx as integer) = bridge.nx
       and cast(grid.ny as integer) = bridge.ny
    inner join canonical
        on bridge.admin_dong_code = canonical.admin_dong_code
)

select
    actual.product_row_id,
    cast('forecast_lineage_not_backed_by_one_grid_row' as varchar) as failure_reason
from actual_lineage_payloads as actual
left join lineage_grid_payloads as backed
    on actual.lineage_payload = backed.lineage_payload
where backed.lineage_payload is null
{% else %}
select cast(null as varchar) as product_row_id,
       cast(null as varchar) as failure_reason
where false
{% endif %}
