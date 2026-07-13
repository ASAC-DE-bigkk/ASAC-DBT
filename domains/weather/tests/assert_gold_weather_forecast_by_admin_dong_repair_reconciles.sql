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

ranked_candidates as (
    select
        joined_candidates.*,
        row_number() over (
            partition by admin_dong_code, forecast_at, category
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
    from joined_candidates
),

boundary_expected as (
    select
        concat(
            admin_dong_code,
            '|',
            to_iso8601(cast(forecast_at as timestamp(6))),
            '|',
            category
        ) as product_row_id,
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
    from ranked_candidates
    where product_row_num = 1
),

actual as (
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
    from {{ ref('gold_weather_forecast_by_admin_dong') }}
),

strictly_newer_targets as (
    select
        expected.admin_dong_code,
        expected.forecast_at,
        expected.category
    from boundary_expected as expected
    inner join actual
        on expected.admin_dong_code = actual.admin_dong_code
       and expected.forecast_at = actual.forecast_at
       and expected.category = actual.category
    where {{ weather_w2_gold_winner_is_not_older('actual', 'expected') }}
      and not {{ weather_w2_gold_winner_is_not_older('expected', 'actual') }}
      and (
          actual.published_at < timestamp '{{ weather_w2_repair_start_at() }}'
          or actual.published_at > timestamp '{{ weather_w2_publishable_cutoff_at() }}'
          or exists (
              select 1
              from eligible_manifest_anchors as anchor
              where anchor.anchor_source_id = actual.source_id
                and anchor.anchor_dag_run_id = actual.dag_run_id
          )
      )
),

expected_scoped as (
    select expected.*
    from boundary_expected as expected
    left join strictly_newer_targets as newer
        on expected.admin_dong_code = newer.admin_dong_code
       and expected.forecast_at = newer.forecast_at
       and expected.category = newer.category
    where newer.admin_dong_code is null
),

actual_scoped as (
    select actual.*
    from actual
    left join strictly_newer_targets as newer
        on actual.admin_dong_code = newer.admin_dong_code
       and actual.forecast_at = newer.forecast_at
       and actual.category = newer.category
    where newer.admin_dong_code is null
      and (
          (
              actual.published_at >= timestamp '{{ weather_w2_repair_start_at() }}'
              and actual.published_at <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
          )
          or exists (
              select 1
              from expected_scoped as expected
              where expected.admin_dong_code = actual.admin_dong_code
                and expected.forecast_at = actual.forecast_at
                and expected.category = actual.category
          )
      )
),

missing as (
    select * from expected_scoped
    except
    select * from actual_scoped
),

extra as (
    select * from actual_scoped
    except
    select * from expected_scoped
)

select * from missing
union all
select * from extra
{% else %}
select cast(null as varchar) as failure_reason
where false
{% endif %}
