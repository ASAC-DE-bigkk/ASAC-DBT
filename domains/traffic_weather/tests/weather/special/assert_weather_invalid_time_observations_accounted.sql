with latest_manifest_state as (
    {{ latest_manifest_run_state('weather_bronze', 'collection_run_manifest', 'kma_vilage_fcst') }}
),

manifest as (
    select source_id, dag_run_id
    from latest_manifest_state
    where manifest_status = 'SUCCESS'
      and is_publishable
),
source_typed as (
    select
        cast(bronze.dag_run_id as varchar) as dag_run_id,
        cast(bronze.raw_object_key as varchar) as raw_object_key,
        case when try_cast(bronze.page_no as integer) > 0
             then try_cast(bronze.page_no as integer) else 0 end as page_no,
        {{ weather_kma_item_signature(
            'bronze.base_date', 'bronze.base_time', 'bronze.nx', 'bronze.ny',
            'bronze.category', 'bronze.fcst_date', 'bronze.fcst_time', 'bronze.fcst_value'
        ) }} as source_item_key,
        {{ asac_axes.kst_at_from_parts('bronze.base_date', 'bronze.base_time') }} as issued_at,
        {{ asac_axes.kst_at_from_parts('bronze.fcst_date', 'bronze.fcst_time') }} as forecast_at
    from {{ source('weather_bronze', 'kma_vilage_fcst') }} bronze
    join manifest
      on cast(bronze.source_id as varchar) = manifest.source_id
     and cast(bronze.dag_run_id as varchar) = manifest.dag_run_id
    where cast(bronze.result_code as varchar) = '00'
),
expected_invalid as (
    select distinct dag_run_id, raw_object_key, page_no, source_item_key
    from source_typed
    where issued_at is null or forecast_at is null
),
actual_invalid as (
    select dag_run_id, raw_object_key, page_no, source_item_key
    from {{ ref('silver_kma_vilage_fcst_observation') }}
    where time_parse_state = 'invalid'
),
missing as (select * from expected_invalid except select * from actual_invalid),
extra as (select * from actual_invalid except select * from expected_invalid),
invalid_in_grid as (
    select grid.selected_dag_run_id as dag_run_id,
           grid.selected_raw_object_key as raw_object_key,
           grid.selected_page_no as page_no,
           grid.selected_source_item_key as source_item_key
    from {{ ref('silver_kma_vilage_fcst_grid') }} grid
    join actual_invalid invalid
      on grid.selected_dag_run_id = invalid.dag_run_id
     and grid.selected_raw_object_key = invalid.raw_object_key
     and grid.selected_page_no = invalid.page_no
     and grid.selected_source_item_key = invalid.source_item_key
),
unknown_state as (
    select dag_run_id, raw_object_key, page_no, source_item_key
    from {{ ref('silver_kma_vilage_fcst_observation') }}
    where time_parse_state not in ('valid', 'invalid') or time_parse_state is null
)
select * from missing
union all select * from extra
union all select * from invalid_in_grid
union all select * from unknown_state
