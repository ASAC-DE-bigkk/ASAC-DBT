-- W1 observation history: publishable run/raw page에서 관측된 동일 KMA item signature 한 행.
{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['dag_run_id', 'raw_object_key', 'page_no', 'source_item_key'],
    on_schema_change='fail',
    views_enabled=false,
    on_table_exists='drop',
    full_refresh=false,
) }}

{{ weather_w1_initial_build_guard() }}
{{ weather_w2_assert_repair_evidence() }}

with publishable_manifest_ranked as (
    select
        cast(source_id as varchar) as source_id,
        cast(dag_run_id as varchar) as dag_run_id,
        cast(dag_id as varchar) as collection_dag_id,
        cast(status as varchar) as manifest_status,
        cast(is_publishable as boolean) as is_publishable,
        cast(expected_rows as bigint) as manifest_expected_rows,
        cast(actual_rows as bigint) as manifest_actual_rows,
        cast(expected_raw_objects as bigint) as manifest_expected_raw_objects,
        cast(actual_raw_objects as bigint) as manifest_actual_raw_objects,
        cast(failure_reason as varchar) as manifest_failure_reason,
        cast(event_at as timestamp(6)) as manifest_event_at_utc,
        row_number() over (
            partition by cast(source_id as varchar), cast(dag_run_id as varchar)
            order by cast(event_at as timestamp(6)) desc, cast(dag_id as varchar) desc
            {% if weather_w2_is_repair() %}, cast(status as varchar) desc{% endif %}
        ) as manifest_row_num
    from {{ source('weather_bronze', 'collection_run_manifest') }}
    where cast(source_id as varchar) = 'kma_vilage_fcst'
    {% if weather_w2_is_repair() %}
      and cast(event_at as timestamp(6)) + interval '9' hour
          <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
    {% else %}
      and cast(status as varchar) = 'SUCCESS'
      and cast(is_publishable as boolean)
    {% endif %}
),

publishable_manifest as (
    select *
    from publishable_manifest_ranked
    where manifest_row_num = 1
    {% if weather_w2_is_repair() %}
      and manifest_status = 'SUCCESS'
      and is_publishable
      and manifest_event_at_utc + interval '9' hour
          >= timestamp '{{ weather_w2_repair_start_at() }}'
      and manifest_event_at_utc + interval '9' hour
          <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
    {% endif %}
),

bronze_typed as (
    select
        cast(bronze.request_id as varchar) as request_id,
        cast(bronze.source_id as varchar) as source_id,
        cast(bronze.place_id as varchar) as place_id,
        cast(bronze.request_params_json as varchar) as request_params_json,
        cast(bronze.base_date as varchar) as base_date,
        cast(bronze.base_time as varchar) as base_time,
        try_cast(bronze.nx as integer) as nx,
        try_cast(bronze.ny as integer) as ny,
        cast(bronze.category as varchar) as category_raw,
        upper(nullif(trim(cast(bronze.category as varchar)), '')) as category,
        cast(bronze.fcst_date as varchar) as fcst_date,
        cast(bronze.fcst_time as varchar) as fcst_time,
        cast(bronze.fcst_value as varchar) as fcst_value_raw,
        cast(bronze.result_code as varchar) as result_code,
        cast(bronze.result_msg as varchar) as result_msg,
        cast(bronze.raw_object_key as varchar) as raw_object_key,
        cast(bronze.payload_hash as varchar) as payload_hash,
        cast(bronze.http_status as integer) as http_status,
        cast(bronze.total_count as bigint) as total_count,
        cast(bronze.item_count as bigint) as item_count,
        try_cast(bronze.page_no as integer) as source_page_no,
        case
            when bronze.page_no is null then 0
            when try_cast(bronze.page_no as integer) > 0 then try_cast(bronze.page_no as integer)
            else 0
        end as page_no,
        case
            when bronze.page_no is null then 'missing_legacy'
            when try_cast(bronze.page_no as integer) > 0 then 'valid_positive'
            else 'invalid'
        end as page_no_state,
        cast(bronze.collected_at as timestamp(6)) as bronze_collected_at_utc,
        cast(bronze.load_date as varchar) as load_date,
        cast(bronze.dag_run_id as varchar) as dag_run_id,
        manifest.collection_dag_id,
        manifest.manifest_status,
        manifest.is_publishable,
        manifest.manifest_expected_rows,
        manifest.manifest_actual_rows,
        manifest.manifest_expected_raw_objects,
        manifest.manifest_actual_raw_objects,
        manifest.manifest_failure_reason,
        manifest.manifest_event_at_utc
    from {{ source('weather_bronze', 'kma_vilage_fcst') }} as bronze
    inner join publishable_manifest as manifest
        on cast(bronze.source_id as varchar) = manifest.source_id
       and cast(bronze.dag_run_id as varchar) = manifest.dag_run_id
    where cast(bronze.result_code as varchar) = '00'
    {% if is_incremental() and not weather_w2_is_repair() %}
      and cast(bronze.collected_at as timestamp(6)) >= (
          select coalesce(max(bronze_collected_at_utc), timestamp '1970-01-01 00:00:00')
                 - interval '{{ weather_w1_lookback_minutes() }}' minute
          from {{ this }}
      )
    {% endif %}
),

identified as (
    select
        *,
        {{ weather_kma_item_key_version() }} as source_item_key_version,
        {{ weather_kma_item_signature(
            'base_date', 'base_time', 'nx', 'ny', 'category_raw',
            'fcst_date', 'fcst_time', 'fcst_value_raw'
        ) }} as source_item_key,
        {{ asac_axes.kst_at_from_parts('base_date', 'base_time') }} as issued_at,
        {{ asac_axes.kst_at_from_parts('fcst_date', 'fcst_time') }} as forecast_at,
        {{ asac_axes.utc_to_kst('bronze_collected_at_utc') }} as collected_at,
        {{ asac_axes.utc_to_kst('manifest_event_at_utc') }} as published_at
    from bronze_typed
),

folded as (
    select
        *,
        count(*) over (
            partition by dag_run_id, raw_object_key, page_no, source_item_key
        ) as source_duplicate_count,
        row_number() over (
            partition by dag_run_id, raw_object_key, page_no, source_item_key
            order by request_id desc, place_id desc
        ) as observation_row_num
    from identified
)

select
    dag_run_id,
    raw_object_key,
    page_no,
    source_item_key,
    source_item_key_version,
    source_page_no,
    page_no_state,
    source_duplicate_count,
    request_id,
    source_id,
    place_id,
    request_params_json,
    base_date,
    base_time,
    nx,
    ny,
    category,
    category_raw,
    fcst_date,
    fcst_time,
    fcst_value_raw,
    issued_at,
    forecast_at,
    forecast_at as event_at,
    case when issued_at is not null then 'valid' else 'invalid' end as issued_time_parse_state,
    case when forecast_at is not null then 'valid' else 'invalid' end as forecast_time_parse_state,
    case when issued_at is not null and forecast_at is not null then 'valid' else 'invalid' end as time_parse_state,
    case when nx > 0 and ny > 0 then 'valid' else 'invalid' end as grid_coordinate_state,
    case when category is not null then 'valid' else 'missing' end as grid_category_state,
    case when issued_at is not null and forecast_at is not null then 'valid' else 'invalid' end as grid_time_state,
    case
        when nx > 0 and ny > 0
         and category is not null
         and issued_at is not null
         and forecast_at is not null
        then 'eligible'
        else 'excluded'
    end as grid_eligibility_state,
    result_code,
    result_msg,
    http_status,
    payload_hash,
    total_count,
    item_count,
    load_date,
    bronze_collected_at_utc,
    manifest_event_at_utc,
    collected_at,
    published_at,
    collection_dag_id,
    manifest_status,
    is_publishable,
    manifest_expected_rows,
    manifest_actual_rows,
    manifest_expected_raw_objects,
    manifest_actual_raw_objects,
    manifest_failure_reason
from folded
where observation_row_num = 1
