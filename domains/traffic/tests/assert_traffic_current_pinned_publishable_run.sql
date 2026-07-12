{% set snapshot_dag_run_id = var('traffic_snapshot_dag_run_id') %}

with manifest_event_values as (
    select distinct
        cast(dag_run_id as varchar) as dag_run_id,
        cast(event_at as timestamp(6)) as event_at,
        cast(status as varchar) as status,
        cast(is_publishable as boolean) as is_publishable
    from {{ source('traffic_bronze', 'collection_run_manifest') }}
    where source_id = 'seoul_traffic_incident'
),

manifest_events as (
    select
        *,
        row_number() over (
            partition by dag_run_id
            order by event_at desc, is_publishable asc, status asc
        ) as manifest_event_rank
    from manifest_event_values
),

publishable_runs as (
    select
        dag_run_id,
        event_at,
        row_number() over (
            order by event_at desc, dag_run_id desc
        ) as publishable_rank
    from manifest_events
    where manifest_event_rank = 1
      and status = 'SUCCESS'
      and is_publishable
),

configured_run as (
    select '{{ snapshot_dag_run_id | replace("'", "''") }}' as dag_run_id
),

pinned_run as (
    select
        publishable_runs.dag_run_id,
        publishable_runs.publishable_rank
    from publishable_runs
    inner join configured_run
        on publishable_runs.dag_run_id = configured_run.dag_run_id
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
        cast(null as varchar) as source_record_id,
        cast(null as varchar) as current_dag_run_id,
        configured_run.dag_run_id as expected_dag_run_id
    from configured_run
    left join pinned_run
        on configured_run.dag_run_id = pinned_run.dag_run_id
    where pinned_run.dag_run_id is null
),

stale_rows as (
    select
        'stale_or_mixed_current_row' as violation_type,
        cast(current.source_record_id as varchar) as source_record_id,
        cast(current.dag_run_id as varchar) as current_dag_run_id,
        pinned_run.dag_run_id as expected_dag_run_id
    from {{ ref('silver_seoul_traffic_incident_current') }} as current
    cross join pinned_run
    where cast(current.dag_run_id as varchar) is distinct from pinned_run.dag_run_id
),

missing_rows as (
    select
        'missing_current_row' as violation_type,
        source_record_id,
        cast(null as varchar) as current_dag_run_id,
        pinned_run.dag_run_id as expected_dag_run_id
    from (
        select *
        from expected_current
        except
        select *
        from actual_current
    ) as missing
    cross join pinned_run
),

extra_rows as (
    select
        'extra_current_row' as violation_type,
        source_record_id,
        cast(null as varchar) as current_dag_run_id,
        pinned_run.dag_run_id as expected_dag_run_id
    from (
        select *
        from actual_current
        except
        select *
        from expected_current
    ) as extra
    cross join pinned_run
),

stale_freshness as (
    select
        'pinned_run_outside_freshness_grace' as violation_type,
        cast(null as varchar) as source_record_id,
        cast(null as varchar) as current_dag_run_id,
        pinned_run.dag_run_id as expected_dag_run_id
    from pinned_run
    where publishable_rank > 3
)

select * from missing_pinned_run
union all
select * from stale_rows
union all
select * from missing_rows
union all
select * from extra_rows
union all
select * from stale_freshness
