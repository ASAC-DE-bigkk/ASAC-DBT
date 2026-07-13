-- depends_on: {{ ref('gold_weather_forecast_by_admin_dong') }}

{% set canonical_contract = weather_w2_canonical_contract() %}

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
    select cast(admin_dong_code as varchar) as admin_dong_code
    from {{ ref('asac_axes', 'dim_admin_dong') }}
    where cast(revision_date as date) = date '{{ canonical_contract['revision_date'] }}'
),

{% if weather_w2_is_repair() %}
eligible_manifest_anchors as (
    {{ weather_w2_latest_publishable_anchors_sql() }}
),
{% endif %}

grid_candidates as (
    select
        bridge.admin_dong_code,
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

ranked as (
    select
        grid_candidates.*,
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
    from grid_candidates
),

expected as (
    select
        admin_dong_code,
        forecast_at,
        category,
        bridge_version,
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
        raw_object_key,
        request_id,
        dag_run_id,
        source_grid_place_id,
        nx,
        ny
    from ranked
    where product_row_num = 1
),

actual as (
    select
        admin_dong_code,
        forecast_at,
        category,
        bridge_version,
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
        raw_object_key,
        request_id,
        dag_run_id,
        source_grid_place_id,
        nx,
        ny
    from {{ ref('gold_weather_forecast_by_admin_dong') }}
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
{% if weather_w2_is_repair() %}
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
