with bronze as (
    select
        trim(cast(event_id as varchar)) as event_id,
        lower(trim(cast(event_type as varchar))) as event_type,
        cast(event_ts as timestamp(6)) as event_ts,
        cast(payload as varchar) as payload,
        cast(raw_object_key as varchar) as raw_object_key,
        cast(ingested_at as timestamp(6)) as ingested_at,
        cast(dag_run_id as varchar) as dag_run_id
    from {{ source('bronze', 'sample_events') }}
),

ranked as (
    select
        *,
        row_number() over (
            partition by event_id
            order by ingested_at desc, raw_object_key desc, dag_run_id desc
        ) as row_num
    from bronze
    where event_id is not null
)

select
    event_id,
    event_type,
    event_ts,
    payload,
    raw_object_key,
    ingested_at,
    dag_run_id
from ranked
where row_num = 1
