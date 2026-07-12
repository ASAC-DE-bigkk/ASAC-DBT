{% set snapshot_dag_run_id = var('traffic_snapshot_dag_run_id') %}

with pinned_run as (
    select cast(dag_run_id as varchar) as dag_run_id
    from {{ source('traffic_bronze', 'collection_run_manifest') }}
    where source_id = 'seoul_traffic_incident'
      and status = 'SUCCESS'
      and is_publishable
      and cast(dag_run_id as varchar) = '{{ snapshot_dag_run_id | replace("'", "''") }}'
),

latest_bronze as (
    select distinct cast(bronze.acc_id as varchar) as source_record_id
    from {{ source('traffic_bronze', 'seoul_traffic_incident') }} as bronze
    inner join pinned_run
        on cast(bronze.dag_run_id as varchar) = pinned_run.dag_run_id
    where cast(bronze.result_code as varchar) = 'INFO-000'
      and cast(bronze.acc_id as varchar) is not null
      and {{ asac_axes.kst_at_from_parts('cast(bronze.occr_date as varchar)', 'cast(bronze.occr_time as varchar)') }} is not null
),

stale_rows as (
    select
        current.source_record_id,
        current.dag_run_id,
        pinned_run.dag_run_id as expected_dag_run_id
    from {{ ref('silver_seoul_traffic_incident_current') }} as current
    cross join pinned_run
    where current.dag_run_id <> pinned_run.dag_run_id
),

missing_rows as (
    select
        latest_bronze.source_record_id,
        cast(null as varchar) as current_dag_run_id,
        pinned_run.dag_run_id as expected_dag_run_id
    from latest_bronze
    cross join pinned_run
    left join {{ ref('silver_seoul_traffic_incident_current') }} as current
        on current.source_record_id = latest_bronze.source_record_id
    where current.source_record_id is null
)

select *
from stale_rows
union all
select *
from missing_rows
