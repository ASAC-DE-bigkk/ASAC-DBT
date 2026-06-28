with kma as (
    select
        source_id,
        forecast_at as service_time,
        raw_object_key,
        collected_at
    from {{ ref('silver_kma_vilage_fcst') }}
),

traffic as (
    select
        source_id,
        occurred_at as service_time,
        raw_object_key,
        collected_at
    from {{ ref('silver_seoul_traffic_incident') }}
),

combined as (
    select * from kma
    union all
    select * from traffic
)

select
    source_id,
    count(*) as row_count,
    count(distinct raw_object_key) as raw_object_count,
    min(service_time) as first_service_time,
    max(service_time) as last_service_time,
    max(collected_at) as last_collected_at
from combined
group by source_id
