with latest_run as (
    select cast(dag_run_id as varchar) as dag_run_id
    from {{ source('traffic_bronze', 'collection_run_manifest') }}
    where source_id = 'seoul_traffic_incident'
      and status = 'SUCCESS'
      and is_publishable
    order by cast(event_at as timestamp(6)) desc, cast(dag_run_id as varchar) desc
    limit 1
),

latest_bronze as (
    select distinct cast(bronze.acc_id as varchar) as source_record_id
    from {{ source('traffic_bronze', 'seoul_traffic_incident') }} as bronze
    inner join latest_run
        on cast(bronze.dag_run_id as varchar) = latest_run.dag_run_id
    where cast(bronze.result_code as varchar) = 'INFO-000'
      and cast(bronze.acc_id as varchar) is not null
      and {{ asac_axes.kst_at_from_parts('cast(bronze.occr_date as varchar)', 'cast(bronze.occr_time as varchar)') }} is not null
),

stale_rows as (
    select
        current.source_record_id,
        current.dag_run_id,
        latest_run.dag_run_id as expected_dag_run_id
    from {{ ref('silver_seoul_traffic_incident_current') }} as current
    cross join latest_run
    where current.dag_run_id <> latest_run.dag_run_id
),

missing_rows as (
    select
        latest_bronze.source_record_id,
        cast(null as varchar) as current_dag_run_id,
        latest_run.dag_run_id as expected_dag_run_id
    from latest_bronze
    cross join latest_run
    left join {{ ref('silver_seoul_traffic_incident_current') }} as current
        on current.source_record_id = latest_bronze.source_record_id
    where current.source_record_id is null
)

select *
from stale_rows
union all
select *
from missing_rows
