-- depends_on: {{ ref('weather_w2_observation_recovery_lineage_workset') }}
-- depends_on: {{ ref('gold_weather_forecast_by_admin_dong') }}
-- depends_on: {{ ref('bridge_weather_admin_dong_grid') }}
-- depends_on: {{ ref('asac_axes', 'dim_admin_dong') }}
-- depends_on: {{ ref('silver_kma_vilage_fcst_grid') }}

{% set canonical_contract = weather_w2_canonical_contract() %}
{% set lineage_run_bucket_count = var('weather_w2_lineage_run_bucket_count', 1) | int %}
{% set lineage_run_bucket_index = var('weather_w2_lineage_run_bucket_index', 0) | int %}

{% if lineage_run_bucket_count < 1
    or lineage_run_bucket_index < 0
    or lineage_run_bucket_index >= lineage_run_bucket_count %}
    {{ exceptions.raise_compiler_error(
        'Weather W2 lineage run bucket은 0 이상 count 미만이어야 합니다.'
    ) }}
{% endif %}

{% if weather_w2_is_repair() %}
with active_bridge as (
    select
        cast(source_admin_code as varchar) as admin_dong_code,
        cast(bridge_version as varchar) as bridge_version,
        cast(nx as integer) as nx,
        cast(ny as integer) as ny
    from {{ ref('bridge_weather_admin_dong_grid') }}
    where cast(bridge_version as varchar) = '{{ weather_w2_bridge_version() }}'
),

canonical as (
    select cast(admin_dong_code as varchar) as admin_dong_code
    from {{ ref('asac_axes', 'dim_admin_dong') }}
    where cast(revision_date as date) = date '{{ canonical_contract['revision_date'] }}'
),

workset_for_window as (
    select
        cast(product_row_id as varchar) as product_row_id,
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(source_id as varchar) as source_id,
        cast(dag_run_id as varchar) as dag_run_id,
        cast(nx as integer) as nx,
        cast(ny as integer) as ny,
        cast(source_grid_place_id as varchar) as source_grid_place_id,
        cast(forecast_at as timestamp(6)) as forecast_at,
        cast(category as varchar) as category,
        cast(issued_at as timestamp(6)) as issued_at,
        cast(collected_at as timestamp(6)) as collected_at,
        cast(published_at as timestamp(6)) as published_at,
        cast(raw_object_key as varchar) as raw_object_key,
        cast(request_id as varchar) as request_id,
        cast(lineage_run_bucket_ordinal as bigint) as lineage_run_bucket_ordinal,
        cast(lineage_payload as varchar) as lineage_payload
    from {{ ref('weather_w2_observation_recovery_lineage_workset') }}
    where cast(repair_start_at as timestamp(6))
          = timestamp '{{ weather_w2_repair_start_at() }}'
      and cast(repair_cutoff_at as timestamp(6))
          = timestamp '{{ weather_w2_publishable_cutoff_at() }}'
),

selected_workset as (
    select *
    from workset_for_window
    where mod(lineage_run_bucket_ordinal, {{ lineage_run_bucket_count }})
          = {{ lineage_run_bucket_index }}
),

lineage_backed_products as (
    select distinct actual.product_row_id
    from selected_workset as actual
    inner join active_bridge as bridge
        on bridge.admin_dong_code = actual.admin_dong_code
    inner join canonical
        on bridge.admin_dong_code = canonical.admin_dong_code
    inner join {{ ref('silver_kma_vilage_fcst_grid') }} as grid
        on cast(grid.source_id as varchar) = actual.source_id
       and cast(grid.selected_dag_run_id as varchar) = actual.dag_run_id
       -- These keys are non-null under the Gold repair contract. They keep
       -- each source/run join at row granularity; JSON below retains null-safe
       -- equality for nullable forecast-value fields.
       and cast(grid.nx as integer) = actual.nx
       and cast(grid.ny as integer) = actual.ny
       and cast(grid.source_grid_place_id as varchar) = actual.source_grid_place_id
       and cast(grid.forecast_at as timestamp(6)) = actual.forecast_at
       and cast(grid.category as varchar) = actual.category
       and cast(grid.issued_at as timestamp(6)) = actual.issued_at
       and cast(grid.collected_at as timestamp(6)) = actual.collected_at
       and cast(grid.published_at as timestamp(6)) = actual.published_at
       and cast(grid.raw_object_key as varchar) = actual.raw_object_key
       and cast(grid.request_id as varchar) = actual.request_id
       -- JSON preserves null-safe exact-row equality while source/run remain
       -- hash keys that bound the Silver Grid side of this validation.
       and json_format(cast(row(
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
        ) as json)) = actual.lineage_payload
)

select
    actual.product_row_id,
    cast('forecast_lineage_not_backed_by_one_grid_row' as varchar) as failure_reason
from selected_workset as actual
left join lineage_backed_products as backed
    on actual.product_row_id = backed.product_row_id
where backed.product_row_id is null
{% if lineage_run_bucket_index == 0 %}
union all
select
    cast(null as varchar) as product_row_id,
    cast('lineage_workset_window_missing' as varchar) as failure_reason
where not exists (select 1 from workset_for_window)
{% endif %}
{% else %}
select cast(null as varchar) as product_row_id,
       cast(null as varchar) as failure_reason
where false
{% endif %}
