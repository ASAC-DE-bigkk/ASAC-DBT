with publishable_runs as (
    select distinct cast(dag_run_id as varchar) as dag_run_id
    from {{ source('traffic_bronze', 'collection_run_manifest') }}
    where source_id = 'seoul_traffic_incident'
      and status = 'SUCCESS'
      and is_publishable
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
    inner join publishable_runs
        on cast(bronze.dag_run_id as varchar) = publishable_runs.dag_run_id
    where cast(bronze.result_code as varchar) = 'INFO-000'
      and cast(bronze.acc_id as varchar) is not null
      and {{ topis_timestamp('cast(bronze.occr_date as varchar)', 'cast(bronze.occr_time as varchar)') }} is not null
),

bronze_latest as (
    select *
    from bronze_candidates
    where row_num = 1
)

select
    silver.source_record_id,
    silver.request_id as silver_request_id,
    bronze_latest.request_id as expected_request_id,
    silver.raw_object_key as silver_raw_object_key,
    bronze_latest.raw_object_key as expected_raw_object_key,
    silver.collected_at as silver_collected_at,
    bronze_latest.collected_at as expected_collected_at
from {{ ref('silver_seoul_traffic_incident') }} as silver
inner join bronze_latest
    on silver.source_record_id = bronze_latest.source_record_id
where silver.request_id <> bronze_latest.request_id
   or silver.raw_object_key <> bronze_latest.raw_object_key
   or silver.collected_at <> bronze_latest.collected_at
