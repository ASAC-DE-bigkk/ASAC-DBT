-- depends_on: {{ ref('weather_w2_observation_recovery_stage') }}
-- depends_on: {{ ref('bridge_weather_admin_dong_grid') }}
-- depends_on: {{ ref('silver_kma_vilage_fcst_grid') }}

{% set repair_mode = weather_w2_is_repair() %}
{% if repair_mode %}
{% set checkpoint_id = weather_w2_recovery_checkpoint_id() %}
{% set target_admin_dong_code = weather_w2_recovery_target_admin_dong_code() %}
{% set lineage_run_bucket_count = var(
    'weather_w2_lineage_run_bucket_count',
    4
) | int %}
{% set lineage_run_bucket_index = var(
    'weather_w2_lineage_run_bucket_index',
    0
) | int %}

{% if lineage_run_bucket_count < 1
    or lineage_run_bucket_index < 0
    or lineage_run_bucket_index >= lineage_run_bucket_count %}
  {{ exceptions.raise_compiler_error(
      'Weather W2 staged lineage bucket index must be inside bucket count.'
  ) }}
{% endif %}

with active_bridge as (
    select
        cast(source_admin_code as varchar) as admin_dong_code,
        cast(bridge_version as varchar) as bridge_version,
        cast(nx as integer) as nx,
        cast(ny as integer) as ny
    from {{ weather_w2_bridge_at_snapshot() }}
    where cast(source_admin_code as varchar) = '1123053600'
      and cast(source_admin_code as varchar) = '{{ target_admin_dong_code }}'
      and cast(nx as integer) = 61
      and cast(ny as integer) = 127
),
stage_rows as (
    select *
    from {{ ref('weather_w2_observation_recovery_stage') }}
    where checkpoint_id = '{{ checkpoint_id }}'
      and admin_dong_code = '1123053600'
),
lineage_runs as (
    select
        source_id,
        dag_run_id,
        row_number() over (order by source_id, dag_run_id) - 1
            as lineage_run_bucket_ordinal
    from (
        select distinct source_id, dag_run_id
        from stage_rows
    )
),
selected_stage as (
    select stage.*
    from stage_rows as stage
    inner join lineage_runs as run
        on stage.source_id = run.source_id
       and stage.dag_run_id = run.dag_run_id
    where mod(
        run.lineage_run_bucket_ordinal,
        {{ lineage_run_bucket_count }}
    ) = {{ lineage_run_bucket_index }}
),
lineage_backed as (
    select distinct stage.product_row_id
    from selected_stage as stage
    inner join active_bridge as bridge
        on stage.admin_dong_code = bridge.admin_dong_code
       and stage.nx = bridge.nx
       and stage.ny = bridge.ny
    inner join {{ weather_w2_silver_grid_at_snapshot() }} as grid
        on cast(grid.source_id as varchar) = stage.source_id
       and cast(grid.selected_dag_run_id as varchar) = stage.dag_run_id
       and cast(grid.nx as integer) = stage.nx
       and cast(grid.ny as integer) = stage.ny
       and cast(grid.source_grid_place_id as varchar) = stage.source_grid_place_id
       and cast(grid.forecast_at as timestamp(6)) = stage.forecast_at
       and cast(grid.category as varchar) = stage.category
       and cast(grid.issued_at as timestamp(6)) = stage.issued_at
       and cast(grid.collected_at as timestamp(6)) = stage.collected_at
       and cast(grid.published_at as timestamp(6)) = stage.published_at
       and cast(grid.raw_object_key as varchar) = stage.raw_object_key
       and cast(grid.request_id as varchar) = stage.request_id
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
        ) as json)) = json_format(cast(row(
            stage.admin_dong_code,
            stage.bridge_version,
            stage.nx,
            stage.ny,
            stage.source_grid_place_id,
            stage.forecast_at,
            stage.category,
            stage.issued_at,
            stage.collected_at,
            stage.published_at,
            stage.fcst_value_raw,
            stage.fcst_value_num,
            stage.value_representation,
            stage.value_num,
            stage.value_lower_bound,
            stage.value_upper_bound,
            stage.qualitative_code,
            stage.forecast_lead_hours,
            stage.source_id,
            stage.dag_run_id,
            stage.raw_object_key,
            stage.request_id
        ) as json))
)
select
    stage.product_row_id,
    cast(
        'forecast_lineage_not_backed_by_pinned_grid_row' as varchar
    ) as failure_reason
from selected_stage as stage
left join lineage_backed as backed
    on stage.product_row_id = backed.product_row_id
where backed.product_row_id is null
{% if lineage_run_bucket_index == 0 %}
union all
select
    cast(null as varchar) as product_row_id,
    cast('staged_lineage_source_missing' as varchar) as failure_reason
where not exists (select 1 from stage_rows)
{% endif %}
{% else %}
select
    cast(null as varchar) as product_row_id,
    cast(null as varchar) as failure_reason
where false
{% endif %}
