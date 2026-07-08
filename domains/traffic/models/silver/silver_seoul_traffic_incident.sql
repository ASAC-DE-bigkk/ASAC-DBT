-- silver: latest TOPIS AccInfo incident row by source_record_id(acc_id).
--
-- incremental(merge): scan recent bronze rows only with a 30 minute
-- collected_at lookback, then merge by the output grain source_record_id.
-- Re-reading the lookback is idempotent because the ranked CTE keeps the
-- latest publishable row per acc_id.
--
-- tmp relation must be a TABLE, not a view (views_enabled=false) — 2026-07-07 dev incident:
--  * merging from the inlined __dbt_tmp view duplicated the tm_to_wgs84 expression tree
--    per column reference and failed every run with Trino QUERY_EXCEEDED_COMPILER_LIMIT;
--    materializing the lookback window first keeps the merge source a plain table scan.
--  * R2 Data Catalog additionally kept rejecting the __dbt_tmp *view* create with
--    409 AlreadyExists (phantom record not visible via list/exists) — the table path
--    avoids the catalog view endpoint entirely.
-- on_table_exists='drop': full-refresh rebuild without rename, matching the
-- population silver precedent on this catalog.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['source_record_id'],
    views_enabled=false,
    on_table_exists='drop',
) }}

with publishable_runs as (
    select distinct cast(dag_run_id as varchar) as dag_run_id
    from {{ source('traffic_bronze', 'collection_run_manifest') }}
    where source_id = 'seoul_traffic_incident'
      and status = 'SUCCESS'
      and is_publishable
),

bronze as (
    select
        cast(bronze.request_id as varchar) as request_id,
        cast(bronze.source_id as varchar) as source_id,
        cast(bronze.request_params_json as varchar) as request_params_json,
        cast(bronze.start_index as integer) as start_index,
        cast(bronze.end_index as integer) as end_index,
        cast(bronze.acc_id as varchar) as acc_id,
        cast(bronze.occr_date as varchar) as occr_date,
        cast(bronze.occr_time as varchar) as occr_time,
        cast(bronze.exp_clr_date as varchar) as exp_clr_date,
        cast(bronze.exp_clr_time as varchar) as exp_clr_time,
        cast(bronze.acc_type as varchar) as acc_type,
        cast(bronze.acc_dtype as varchar) as acc_dtype,
        cast(bronze.link_id as varchar) as link_id,
        try_cast(bronze.grs80tm_x as double) as grs80tm_x,
        try_cast(bronze.grs80tm_y as double) as grs80tm_y,
        cast(bronze.acc_info as varchar) as acc_info,
        cast(bronze.acc_road_code as varchar) as acc_road_code,
        cast(bronze.raw_object_key as varchar) as raw_object_key,
        cast(bronze.payload_hash as varchar) as payload_hash,
        cast(bronze.result_code as varchar) as result_code,
        cast(bronze.result_msg as varchar) as result_msg,
        cast(bronze.list_total_count as integer) as list_total_count,
        cast(bronze.row_count as integer) as row_count,
        cast(bronze.collected_at as timestamp(6)) as collected_at,
        cast(bronze.load_date as varchar) as load_date,
        cast(bronze.dag_run_id as varchar) as dag_run_id
    from {{ source('traffic_bronze', 'seoul_traffic_incident') }} as bronze
    inner join publishable_runs
        on cast(bronze.dag_run_id as varchar) = publishable_runs.dag_run_id
    {% if is_incremental() %}
    where cast(bronze.collected_at as timestamp(6)) >= (
        select coalesce(max(collected_at), timestamp '1970-01-01') - interval '30' minute
        from {{ this }}
    )
    {% endif %}
),

standardized as (
    select
        *,
        {{ asac_axes.kst_at_from_parts('occr_date', 'occr_time') }} as occurred_at,
        {{ asac_axes.kst_at_from_parts('exp_clr_date', 'exp_clr_time') }} as expected_clear_at,
        'GRS80_TM' as source_coordinate_system,
        case
            when grs80tm_x is not null and grs80tm_y is not null
                then 'source_coordinate_available'
            else 'source_coordinate_missing'
        end as source_location_quality
    from bronze
    where result_code = 'INFO-000'
),

-- layered variant: inline tm_to_wgs84 exploded the compiled expression (~73KB)
-- past Trino's single-projection codegen limit; see asac_axes.tm_to_wgs84_relation.
located as (
    {{ asac_axes.tm_to_wgs84_relation('standardized', 'grs80tm_x', 'grs80tm_y') }}
),

admin_matched as (
    select
        located.*,
        boundary.admin_dong_code,
        boundary.gu_code,
        boundary.dong as admin_dong,
        boundary.sigungu as gu,
        row_number() over (
            partition by located.acc_id, located.request_id, located.raw_object_key
            order by
                case when boundary.admin_dong_code is null then 1 else 0 end,
                boundary.admin_dong_code
        ) as admin_match_num
    from located
    left join {{ ref('asac_axes', 'seoul_admin_dong_boundary') }} as boundary
        on located.longitude is not null
       and located.latitude is not null
       and boundary.admin_dong_code is not null
       and {{ asac_axes.admin_dong_contains('boundary.boundary_wkt', 'located.longitude', 'located.latitude') }}
),

admin_deduped as (
    select *
    from admin_matched
    where admin_match_num = 1
),

ranked as (
    select
        *,
        row_number() over (
            partition by acc_id
            order by collected_at desc, raw_object_key desc, request_id desc
        ) as row_num
    from admin_deduped
    where acc_id is not null
      and occurred_at is not null
)

select
    request_id,
    source_id,
    request_params_json,
    acc_id as source_record_id,
    acc_type,
    acc_dtype,
    link_id as asset_id,
    acc_road_code,
    acc_info,
    source_coordinate_system,
    source_location_quality,
    grs80tm_x,
    grs80tm_y,
    longitude,
    latitude,
    admin_dong_code,
    gu_code,
    admin_dong,
    gu,
    occurred_at,
    occurred_at as event_at,
    expected_clear_at,
    occurred_at as valid_from,
    expected_clear_at as valid_to,
    date_trunc('hour', occurred_at) as time_bucket,
    raw_object_key,
    payload_hash,
    list_total_count,
    row_count,
    load_date,
    collected_at,
    dag_run_id
from ranked
where row_num = 1
