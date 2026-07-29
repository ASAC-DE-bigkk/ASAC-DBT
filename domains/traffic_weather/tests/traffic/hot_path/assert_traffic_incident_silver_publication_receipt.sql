{% set snapshot_dag_run_id = var('traffic_snapshot_dag_run_id') %}

with latest_manifest_state as (
    {{ latest_manifest_run_state('traffic_bronze', 'collection_run_manifest', 'seoul_traffic_incident') }}
),

configured_run as (
    select '{{ snapshot_dag_run_id | replace("'", "''") }}' as dag_run_id
),

pinned_run as (
    select manifest.dag_run_id
    from latest_manifest_state as manifest
    inner join configured_run
        on manifest.dag_run_id = configured_run.dag_run_id
    where manifest.manifest_status = 'SUCCESS'
      and manifest.is_publishable
),

expected_current as (
    select distinct cast(bronze.acc_id as varchar) as source_record_id
    from {{ source('traffic_bronze', 'seoul_traffic_incident') }} as bronze
    inner join pinned_run
        on cast(bronze.dag_run_id as varchar) = pinned_run.dag_run_id
    where cast(bronze.result_code as varchar) = 'INFO-000'
      and cast(bronze.acc_id as varchar) is not null
      and {{ asac_axes.kst_at_from_parts('cast(bronze.occr_date as varchar)', 'cast(bronze.occr_time as varchar)') }} is not null
),

actual_current as (
    select distinct cast(source_record_id as varchar) as source_record_id
    from {{ ref('silver_seoul_traffic_incident_current') }}
),

missing_pinned_run as (
    select
        'missing_pinned_run' as violation_type,
        cast(null as varchar) as source_record_id
    from configured_run
    left join pinned_run using (dag_run_id)
    where pinned_run.dag_run_id is null
),

stale_or_mixed_current_row as (
    select
        'stale_or_mixed_current_row' as violation_type,
        cast(current.source_record_id as varchar) as source_record_id
    from {{ ref('silver_seoul_traffic_incident_current') }} as current
    cross join pinned_run
    where cast(current.dag_run_id as varchar) is distinct from pinned_run.dag_run_id
),

missing_current_row as (
    select 'missing_current_row' as violation_type, source_record_id
    from (
        select * from expected_current
        except
        select * from actual_current
    )
),

extra_current_row as (
    select 'extra_current_row' as violation_type, source_record_id
    from (
        select * from actual_current
        except
        select * from expected_current
    )
),

invalid_critical_field as (
    select
        'invalid_critical_field' as violation_type,
        cast(source_record_id as varchar) as source_record_id
    from {{ ref('silver_seoul_traffic_incident_current') }}
    where source_record_id is null
       or source_id is null
       or event_at is null
),

duplicate_source_record_id as (
    select
        'duplicate_source_record_id' as violation_type,
        cast(source_record_id as varchar) as source_record_id
    from {{ ref('silver_seoul_traffic_incident_current') }}
    group by source_record_id
    having count(*) > 1
)

select * from missing_pinned_run
union all
select * from stale_or_mixed_current_row
union all
select * from missing_current_row
union all
select * from extra_current_row
union all
select * from invalid_critical_field
union all
select * from duplicate_source_record_id
