-- W2 public Gold: latest canonical admin-dong forecast at product grain.
{{ config(
    materialized='incremental',
    incremental_strategy='weather_w2_reconcile',
    unique_key=['admin_dong_code', 'forecast_at', 'category'],
    on_schema_change='fail',
    views_enabled=false,
    on_table_exists='drop',
    full_refresh=false,
) }}

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
    from {{ ref('asac_axes', 'dim_admin_dong') }} as canonical
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
    from {{ ref('silver_kma_vilage_fcst_grid') }}
    {% if weather_w2_is_repair() %}
    where published_at >= timestamp '{{ weather_w2_repair_start_at() }}'
      and published_at <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
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
),

ranked_candidates as (
    select
        admin_dong_code,
        admin_dong,
        gu_code,
        gu,
        admin_dong_revision_date,
        bridge_version,
        nx,
        ny,
        source_grid_place_id,
        issued_at,
        forecast_at,
        category,
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
        request_id,
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

expected_rows as (
    select
        concat(admin_dong_code, '|', to_iso8601(cast(forecast_at as timestamp(6))), '|', category) as product_row_id,
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
)

{% if is_incremental() %}
,
restamp_rows as (
    select
        target.product_row_id,
        target.admin_dong_code,
        target.forecast_at,
        target.category,
        canonical.admin_dong,
        canonical.gu_code,
        canonical.gu,
        canonical.admin_dong_revision_date,
        target.bridge_version,
        target.nx,
        target.ny,
        target.source_grid_place_id,
        target.issued_at,
        target.collected_at,
        target.published_at,
        target.fcst_value_raw,
        target.fcst_value_num,
        target.value_representation,
        target.value_num,
        target.value_lower_bound,
        target.value_upper_bound,
        target.qualitative_code,
        target.forecast_lead_hours,
        target.source_id,
        target.dag_run_id,
        target.raw_object_key,
        target.request_id
    from {{ this }} as target
    inner join canonical
        on target.admin_dong_code = canonical.admin_dong_code
    where (
        target.admin_dong is distinct from canonical.admin_dong
        or target.gu_code is distinct from canonical.gu_code
        or target.gu is distinct from canonical.gu
        or target.admin_dong_revision_date is distinct from canonical.admin_dong_revision_date
    )
    {% if weather_w2_is_repair() %}
      and not (
          target.published_at >= timestamp '{{ weather_w2_repair_start_at() }}'
          and target.published_at <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
      )
    {% endif %}
      and not exists (
          select 1
          from expected_rows as expected
          where expected.admin_dong_code = target.admin_dong_code
            and expected.forecast_at = target.forecast_at
            and expected.category = target.category
      )
)
{% endif %}
,
product_rows as (
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
    {% if is_incremental() %}
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
    from restamp_rows
    {% endif %}
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
from product_rows
