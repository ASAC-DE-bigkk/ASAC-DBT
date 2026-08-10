with silver_ranked as (
    select
        link_id,
        row_number() over (
            partition by link_id
            order by observed_at desc, raw_object_key desc, request_id desc
        ) as row_num
    from {{ ref('silver_seoul_traffic_flow') }}
),

expected as (
    select link_id
    from silver_ranked
    where row_num = 1
),

actual as (
    select link_id
    from {{ ref('gold_traffic_flow_link_latest') }}
),

missing_from_gold as (
    select link_id from expected
    except
    select link_id from actual
),

added_by_enrichment as (
    select link_id from actual
    except
    select link_id from expected
)

select 'missing_from_gold' as violation, link_id
from missing_from_gold
union all
select 'added_by_enrichment' as violation, link_id
from added_by_enrichment
