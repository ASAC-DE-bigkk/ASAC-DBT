with manifest as (
    select source_id, dag_run_id, expected_rows, actual_rows,
           expected_raw_objects, actual_raw_objects
    from (
        select
            cast(source_id as varchar) as source_id,
            cast(dag_run_id as varchar) as dag_run_id,
            cast(actual_rows as bigint) as actual_rows,
            cast(expected_rows as bigint) as expected_rows,
            cast(expected_raw_objects as bigint) as expected_raw_objects,
            cast(actual_raw_objects as bigint) as actual_raw_objects,
            row_number() over (
                partition by cast(source_id as varchar), cast(dag_run_id as varchar)
                order by cast(event_at as timestamp(6)) desc, cast(dag_id as varchar) desc
            ) as row_num
        from {{ source('weather_bronze', 'collection_run_manifest') }}
        where cast(source_id as varchar) = 'kma_vilage_fcst'
          and cast(status as varchar) = 'SUCCESS'
          and cast(is_publishable as boolean)
    )
    where row_num = 1
),
actual as (
    select source_id, dag_run_id,
           sum(source_duplicate_count) as observation_rows,
           count(distinct raw_object_key) as observation_raw_objects
    from {{ ref('silver_kma_vilage_fcst_observation') }}
    group by 1, 2
),
source_actual as (
    select cast(bronze.source_id as varchar) as source_id,
           cast(bronze.dag_run_id as varchar) as dag_run_id,
           count(*) as source_rows,
           count(distinct cast(bronze.raw_object_key as varchar)) as source_raw_objects
    from {{ source('weather_bronze', 'kma_vilage_fcst') }} bronze
    join manifest
      on cast(bronze.source_id as varchar) = manifest.source_id
     and cast(bronze.dag_run_id as varchar) = manifest.dag_run_id
    where cast(bronze.result_code as varchar) = '00'
    group by 1, 2
),
orphan as (
    select observation.dag_run_id
    from {{ ref('silver_kma_vilage_fcst_observation') }} observation
    left join manifest
      on observation.source_id = manifest.source_id
     and observation.dag_run_id = manifest.dag_run_id
    where manifest.dag_run_id is null
),
count_mismatch as (
    select manifest.dag_run_id
    from manifest
    left join source_actual using (source_id, dag_run_id)
    left join actual using (source_id, dag_run_id)
    where coalesce(actual.observation_rows, 0) is distinct from coalesce(source_actual.source_rows, 0)
       or coalesce(actual.observation_raw_objects, 0) is distinct from coalesce(source_actual.source_raw_objects, 0)
       or manifest.actual_rows is distinct from coalesce(source_actual.source_rows, 0)
       or manifest.actual_raw_objects is distinct from coalesce(source_actual.source_raw_objects, 0)
       or manifest.expected_rows is distinct from manifest.actual_rows
       or manifest.expected_raw_objects is distinct from manifest.actual_raw_objects
)
select * from orphan
union all
select * from count_mismatch
