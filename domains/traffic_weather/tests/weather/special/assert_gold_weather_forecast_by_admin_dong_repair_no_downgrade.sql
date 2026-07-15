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

all_grid_records as (
    select
        bridge.admin_dong_code,
        cast(grid.forecast_at as timestamp(6)) as forecast_at,
        cast(grid.category as varchar) as category,
        bridge.bridge_version,
        cast(grid.nx as integer) as nx,
        cast(grid.ny as integer) as ny,
        cast(grid.source_grid_place_id as varchar) as source_grid_place_id,
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
        cast(grid.selected_dag_run_id as varchar) as dag_run_id,
        cast(grid.raw_object_key as varchar) as raw_object_key,
        cast(grid.request_id as varchar) as request_id
    from {{ ref('silver_kma_vilage_fcst_grid') }} as grid
    inner join active_bridge as bridge
        on cast(grid.nx as integer) = bridge.nx
       and cast(grid.ny as integer) = bridge.ny
    inner join canonical
        on bridge.admin_dong_code = canonical.admin_dong_code
),

repair_candidates as (
    select all_grid_records.*
    from all_grid_records
    inner join eligible_manifest_anchors as anchor
        on all_grid_records.source_id = anchor.anchor_source_id
       and all_grid_records.dag_run_id = anchor.anchor_dag_run_id
    where all_grid_records.published_at
          >= timestamp '{{ weather_w2_repair_start_at() }}'
      and all_grid_records.published_at
          <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
),

ranked_repair_candidates as (
    select
        repair_candidates.*,
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
    from repair_candidates
),

expected as (
    select *
    from ranked_repair_candidates
    where product_row_num = 1
),

actual as (
    select *
    from {{ ref('gold_weather_forecast_by_admin_dong') }}
),

invalid_target_winner as (
    select
        expected.admin_dong_code,
        expected.forecast_at,
        expected.category,
        cast('missing_older_or_ineligible_newer_target' as varchar) as failure_reason
    from expected
    left join actual
        on expected.admin_dong_code = actual.admin_dong_code
       and expected.forecast_at = actual.forecast_at
       and expected.category = actual.category
    where actual.admin_dong_code is null
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
),

mixed_or_unbacked_lineage as (
    select
        actual.admin_dong_code,
        actual.forecast_at,
        actual.category,
        cast('forecast_lineage_not_backed_by_one_grid_row' as varchar) as failure_reason
    from actual
    inner join expected
        on expected.admin_dong_code = actual.admin_dong_code
       and expected.forecast_at = actual.forecast_at
       and expected.category = actual.category
    where {{ weather_w2_gold_winner_is_not_older('actual', 'expected') }}
      and not exists (
          select 1
          from all_grid_records as grid
          where grid.admin_dong_code = actual.admin_dong_code
            and grid.forecast_at = actual.forecast_at
            and grid.category = actual.category
            and grid.bridge_version is not distinct from actual.bridge_version
            and grid.nx is not distinct from actual.nx
            and grid.ny is not distinct from actual.ny
            and grid.source_grid_place_id is not distinct from actual.source_grid_place_id
            and grid.issued_at is not distinct from actual.issued_at
            and grid.collected_at is not distinct from actual.collected_at
            and grid.published_at is not distinct from actual.published_at
            and grid.fcst_value_raw is not distinct from actual.fcst_value_raw
            and grid.fcst_value_num is not distinct from actual.fcst_value_num
            and grid.value_representation is not distinct from actual.value_representation
            and grid.value_num is not distinct from actual.value_num
            and grid.value_lower_bound is not distinct from actual.value_lower_bound
            and grid.value_upper_bound is not distinct from actual.value_upper_bound
            and grid.qualitative_code is not distinct from actual.qualitative_code
            and grid.forecast_lead_hours is not distinct from actual.forecast_lead_hours
            and grid.source_id is not distinct from actual.source_id
            and grid.dag_run_id is not distinct from actual.dag_run_id
            and grid.raw_object_key is not distinct from actual.raw_object_key
            and grid.request_id is not distinct from actual.request_id
      )
)

select * from invalid_target_winner
union all
select * from mixed_or_unbacked_lineage
{% else %}
select cast(null as varchar) as admin_dong_code,
       cast(null as timestamp(6)) as forecast_at,
       cast(null as varchar) as category,
       cast(null as varchar) as failure_reason
where false
{% endif %}
