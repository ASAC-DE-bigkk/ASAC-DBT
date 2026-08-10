{{ config(tags=['traffic_gold_gate']) }}

with silver_hourly as (
    select
        link_id,
        cast(
            date_trunc('hour', {{ asac_axes.utc_to_kst('observed_at') }})
            as timestamp(6)
        ) as hour_at,
        observed_at,
        raw_object_key,
        request_id
    from {{ ref('silver_seoul_traffic_flow') }}
),

silver_ranked as (
    select
        link_id,
        hour_at,
        row_number() over (
            partition by link_id, hour_at
            order by observed_at desc, raw_object_key desc, request_id desc
        ) as row_num
    from silver_hourly
),

expected as (
    select hour_at, link_id
    from silver_ranked
    where row_num = 1
),

actual as (
    select hour_at, link_id
    from {{ ref('gold_traffic_flow_congestion_hotspots_hourly') }}
),

missing_from_gold as (
    select hour_at, link_id from expected
    except
    select hour_at, link_id from actual
),

added_by_enrichment as (
    select hour_at, link_id from actual
    except
    select hour_at, link_id from expected
)

select 'missing_from_gold' as violation, hour_at, link_id
from missing_from_gold
union all
select 'added_by_enrichment' as violation, hour_at, link_id
from added_by_enrichment
