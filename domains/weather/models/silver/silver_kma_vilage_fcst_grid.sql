-- W1 native Grid: eligible observation 중 결정적으로 선택된 KMA 예보 사실 한 행.
{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['nx', 'ny', 'issued_at', 'forecast_at', 'category'],
    on_schema_change='fail',
    views_enabled=false,
    on_table_exists='drop',
    full_refresh=false,
) }}

{{ weather_w1_initial_build_guard() }}
{{ weather_w2_assert_repair_evidence() }}

with eligible as (
    select *
    from {{ ref('silver_kma_vilage_fcst_observation') }}
    where grid_eligibility_state = 'eligible'
    {% if weather_w2_is_repair() %}
      and published_at >= timestamp '{{ weather_w2_repair_start_at() }}'
      and published_at <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
    {% elif is_incremental() %}
      and collected_at >= (
          select coalesce(max(collected_at), timestamp '1970-01-01 00:00:00')
                 - interval '{{ weather_w1_lookback_minutes() }}' minute
          from {{ this }}
      )
    {% endif %}
),

ranked as (
    select
        *,
        row_number() over (
            partition by nx, ny, issued_at, forecast_at, category
            order by collected_at desc, raw_object_key desc, request_id desc, dag_run_id desc, page_no desc, source_item_key desc
        ) as grid_row_num
    from eligible
),

selected as (
    select
        nx,
        ny,
        issued_at,
        forecast_at,
        category,
        category_raw,
        forecast_at as event_at,
        date_trunc('hour', forecast_at) as time_bucket,
        request_id,
        source_id,
        place_id as source_grid_place_id,
        request_params_json,
        fcst_value_raw,
        try_cast(fcst_value_raw as double) as fcst_value_num,
        {{ kma_value_semantics('category', 'fcst_value_raw') }},
        date_diff('hour', issued_at, forecast_at) as forecast_lead_hours,
        dag_run_id as selected_dag_run_id,
        raw_object_key as selected_raw_object_key,
        page_no as selected_page_no,
        source_item_key as selected_source_item_key,
        source_item_key_version,
        request_id as selected_request_id,
        raw_object_key,
        payload_hash,
        page_no,
        source_item_key,
        source_duplicate_count,
        total_count,
        item_count,
        load_date,
        bronze_collected_at_utc,
        manifest_event_at_utc,
        collected_at,
        published_at,
        collection_dag_id
    from ranked
    where grid_row_num = 1
)

select candidate.*
from selected as candidate
{% if is_incremental() and weather_w2_is_repair() %}
where not exists (
    select 1
    from {{ this }} as current
    where current.nx = candidate.nx
      and current.ny = candidate.ny
      and current.issued_at = candidate.issued_at
      and current.forecast_at = candidate.forecast_at
      and current.category = candidate.category
      and {{ weather_w2_grid_winner_is_newer('current', 'candidate') }}
)
{% endif %}
