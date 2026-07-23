-- depends_on: {{ ref('gold_weather_forecast_by_admin_dong') }}

{% set canonical_contract = weather_w2_canonical_contract() %}

with active_bridge as (
    select
        cast(source_admin_code as varchar) as admin_dong_code,
        cast(nx as integer) as nx,
        cast(ny as integer) as ny
    from {{ ref('bridge_weather_admin_dong_grid') }}
    where cast(bridge_version as varchar) = 'weather_admin_dong_grid_bridge_v1'
),

canonical as (
    select cast(admin_dong_code as varchar) as admin_dong_code
    from {{ asac_axes.pinned_dim_admin_dong() }}
    where cast(revision_date as date) = date '{{ canonical_contract['revision_date'] }}'
),

{% if weather_w2_is_repair() %}
eligible_manifest_anchors as (
    {{ weather_w2_latest_publishable_anchors_sql() }}
),
{% endif %}

expected_grains as (
    select distinct
        bridge.admin_dong_code,
        cast(grid.forecast_at as timestamp(6)) as forecast_at,
        cast(grid.category as varchar) as category
    from {{ ref('silver_kma_vilage_fcst_grid') }} as grid
    inner join active_bridge as bridge
        on cast(grid.nx as integer) = bridge.nx
       and cast(grid.ny as integer) = bridge.ny
    inner join canonical
        on bridge.admin_dong_code = canonical.admin_dong_code
    {% if weather_w2_is_repair() %}
    inner join eligible_manifest_anchors as anchor
        on cast(grid.source_id as varchar) = anchor.anchor_source_id
       and cast(grid.selected_dag_run_id as varchar) = anchor.anchor_dag_run_id
    where cast(grid.published_at as timestamp(6))
          >= timestamp '{{ weather_w2_repair_start_at() }}'
      and cast(grid.published_at as timestamp(6))
          <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
    {% endif %}
),

actual_grains as (
    select
        gold.admin_dong_code,
        gold.forecast_at,
        gold.category
    from {{ ref('gold_weather_forecast_by_admin_dong') }} as gold
    {% if weather_w2_is_repair() %}
    where (
        gold.published_at >= timestamp '{{ weather_w2_repair_start_at() }}'
        and gold.published_at <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
    )
       or exists (
           select 1
           from expected_grains as expected
           where expected.admin_dong_code = gold.admin_dong_code
             and expected.forecast_at = gold.forecast_at
             and expected.category = gold.category
       )
    {% endif %}
),

missing as (
    select * from expected_grains
    except
    select * from actual_grains
),

extra as (
    select * from actual_grains
    except
    select * from expected_grains
),

invalid_actual_bridge as (
    select
        gold.admin_dong_code,
        gold.forecast_at,
        gold.category
    from {{ ref('gold_weather_forecast_by_admin_dong') }} as gold
    left join active_bridge as bridge
        on gold.admin_dong_code = bridge.admin_dong_code
       and gold.nx = bridge.nx
       and gold.ny = bridge.ny
    left join canonical
        on gold.admin_dong_code = canonical.admin_dong_code
    {% if weather_w2_is_repair() %}
    where (
        (
            gold.published_at >= timestamp '{{ weather_w2_repair_start_at() }}'
            and gold.published_at <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
        )
        or exists (
            select 1
            from expected_grains as expected
            where expected.admin_dong_code = gold.admin_dong_code
              and expected.forecast_at = gold.forecast_at
              and expected.category = gold.category
        )
    )
      and (
          gold.bridge_version is distinct from 'weather_admin_dong_grid_bridge_v1'
          or bridge.admin_dong_code is null
          or canonical.admin_dong_code is null
      )
    {% else %}
    where gold.bridge_version is distinct from 'weather_admin_dong_grid_bridge_v1'
       or bridge.admin_dong_code is null
       or canonical.admin_dong_code is null
    {% endif %}
)

select * from missing
union all
select * from extra
union all
select * from invalid_actual_bridge
