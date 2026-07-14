-- depends_on: {{ ref('silver_seoul_traffic_incident') }}
-- Verify that history Silver selected the latest valid record per acc_id from
-- the publishable Bronze run pinned by this transform invocation. The model
-- and this test must use the same snapshot: comparing unconsumed five-minute
-- Bronze runs would reintroduce a structural dbt run/test race. Bronze keeps
-- the complete collection history independently.

{% set snapshot_dag_run_id = var('traffic_snapshot_dag_run_id') %}

with requested_run as (
    select '{{ snapshot_dag_run_id | replace("'", "''") }}' as dag_run_id
),

configured_run as (
    select distinct cast(manifest.dag_run_id as varchar) as dag_run_id
    from {{ source('traffic_bronze', 'collection_run_manifest') }} as manifest
    inner join requested_run
        on cast(manifest.dag_run_id as varchar) = requested_run.dag_run_id
    where manifest.source_id = 'seoul_traffic_incident'
      and manifest.status = 'SUCCESS'
      and manifest.is_publishable
),

bronze_candidates as (
    select
        cast(bronze.acc_id as varchar) as source_record_id,
        cast(bronze.request_id as varchar) as request_id,
        cast(bronze.raw_object_key as varchar) as raw_object_key,
        cast(bronze.collected_at as timestamp(6)) as collected_at,
        row_number() over (
            partition by cast(bronze.acc_id as varchar)
            order by
                cast(bronze.collected_at as timestamp(6)) desc,
                cast(bronze.raw_object_key as varchar) desc,
                cast(bronze.request_id as varchar) desc
        ) as row_num
    from {{ source('traffic_bronze', 'seoul_traffic_incident') }} as bronze
    inner join configured_run
        on cast(bronze.dag_run_id as varchar) = configured_run.dag_run_id
    where cast(bronze.result_code as varchar) = 'INFO-000'
      and cast(bronze.acc_id as varchar) is not null
      and {{ asac_axes.kst_at_from_parts('cast(bronze.occr_date as varchar)', 'cast(bronze.occr_time as varchar)') }} is not null
),

bronze_latest as (
    select *
    from bronze_candidates
    where row_num = 1
),

missing_pinned_run as (
    select
        cast('__manifest__' as varchar) as source_record_id,
        cast(null as varchar) as silver_request_id,
        requested_run.dag_run_id as expected_request_id,
        cast(null as varchar) as silver_raw_object_key,
        cast(null as varchar) as expected_raw_object_key,
        cast(null as timestamp(6)) as silver_collected_at,
        cast(null as timestamp(6)) as expected_collected_at
    from requested_run
    left join configured_run
        on requested_run.dag_run_id = configured_run.dag_run_id
    where configured_run.dag_run_id is null
)

select * from missing_pinned_run
union all
select
    bronze_latest.source_record_id,
    silver.request_id as silver_request_id,
    bronze_latest.request_id as expected_request_id,
    silver.raw_object_key as silver_raw_object_key,
    bronze_latest.raw_object_key as expected_raw_object_key,
    silver.collected_at as silver_collected_at,
    bronze_latest.collected_at as expected_collected_at
from bronze_latest
left join {{ ref('silver_seoul_traffic_incident') }} as silver
    on silver.source_record_id = bronze_latest.source_record_id
where silver.source_record_id is null
   or silver.request_id is distinct from bronze_latest.request_id
   or silver.raw_object_key is distinct from bronze_latest.raw_object_key
   or silver.collected_at is distinct from bronze_latest.collected_at
