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

expected_metadata as (
    select 'seoul_traffic_incident' as source_id, dag_run_id
    from configured_run
),

metadata_run as (
    select
        cast(source_id as varchar) as source_id,
        cast(snapshot_dag_run_id as varchar) as dag_run_id
    from {{ target.database }}.{{ target.schema }}.recovery_traffic_snapshot_metadata
),

silver_marker_run as (
    select
        cast(source_id as varchar) as source_id,
        cast(dag_run_id as varchar) as dag_run_id
    from {{ target.database }}.{{ target.schema }}.recovery_silver_seoul_traffic_incident
    where is_snapshot_marker
),

missing_pinned_run as (
    select
        'missing_pinned_run' as violation_type,
        requested_run.dag_run_id as source_record_id,
        cast(null as varchar) as request_id,
        cast(null as varchar) as raw_object_key,
        cast(null as timestamp(6)) as collected_at,
        cast(null as varchar) as dag_run_id
    from requested_run
    left join configured_run
        on requested_run.dag_run_id = configured_run.dag_run_id
    where configured_run.dag_run_id is null
),

metadata_run_mismatch as (
    select
        'metadata_run_mismatch' as violation_type,
        source_id as source_record_id,
        cast(null as varchar) as request_id,
        cast(null as varchar) as raw_object_key,
        cast(null as timestamp(6)) as collected_at,
        dag_run_id
    from (
        select * from expected_metadata
        except
        select * from metadata_run
    )
    where exists (select 1 from configured_run)

    union all

    select
        'metadata_run_mismatch' as violation_type,
        source_id as source_record_id,
        cast(null as varchar) as request_id,
        cast(null as varchar) as raw_object_key,
        cast(null as timestamp(6)) as collected_at,
        dag_run_id
    from (
        select * from metadata_run
        except
        select * from expected_metadata
    )
    where exists (select 1 from configured_run)
),

silver_marker_run_mismatch as (
    select
        'silver_marker_run_mismatch' as violation_type,
        source_id as source_record_id,
        cast(null as varchar) as request_id,
        cast(null as varchar) as raw_object_key,
        cast(null as timestamp(6)) as collected_at,
        dag_run_id
    from (
        select * from metadata_run
        except
        select * from silver_marker_run
    )
    where exists (select 1 from configured_run)

    union all

    select
        'silver_marker_run_mismatch' as violation_type,
        source_id as source_record_id,
        cast(null as varchar) as request_id,
        cast(null as varchar) as raw_object_key,
        cast(null as timestamp(6)) as collected_at,
        dag_run_id
    from (
        select * from silver_marker_run
        except
        select * from metadata_run
    )
    where exists (select 1 from configured_run)
),

expected_current as (
    select
        cast(bronze.acc_id as varchar) as source_record_id,
        cast(bronze.request_id as varchar) as request_id,
        cast(bronze.raw_object_key as varchar) as raw_object_key,
        cast(bronze.collected_at as timestamp(6)) as collected_at,
        cast(bronze.dag_run_id as varchar) as dag_run_id,
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

expected_deduped as (
    select source_record_id, request_id, raw_object_key, collected_at, dag_run_id
    from expected_current
    where row_num = 1
),

actual_current as (
    select
        cast(source_record_id as varchar) as source_record_id,
        cast(request_id as varchar) as request_id,
        cast(raw_object_key as varchar) as raw_object_key,
        cast(collected_at as timestamp(6)) as collected_at,
        cast(dag_run_id as varchar) as dag_run_id
    from {{ target.database }}.{{ target.schema }}.recovery_silver_seoul_traffic_incident
    where not is_snapshot_marker
),

missing_rows as (
    select
        'missing_or_mismatched_recovery_row' as violation_type,
        source_record_id,
        request_id,
        raw_object_key,
        collected_at,
        dag_run_id
    from (
        select * from expected_deduped
        except
        select * from actual_current
    )
    where exists (select 1 from configured_run)
      and not exists (select 1 from metadata_run_mismatch)
      and not exists (select 1 from silver_marker_run_mismatch)
),

extra_rows as (
    select
        'extra_or_mismatched_recovery_row' as violation_type,
        source_record_id,
        request_id,
        raw_object_key,
        collected_at,
        dag_run_id
    from (
        select * from actual_current
        except
        select * from expected_deduped
    )
    where exists (select 1 from configured_run)
      and not exists (select 1 from metadata_run_mismatch)
      and not exists (select 1 from silver_marker_run_mismatch)
)

select * from missing_pinned_run
union all
select * from metadata_run_mismatch
union all
select * from silver_marker_run_mismatch
union all
select * from missing_rows
union all
select * from extra_rows
