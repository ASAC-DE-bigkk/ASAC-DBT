{% set old_schema = var('traffic_gold_old_schema', 'traffic_gold_reference') %}
{% set shadow_schema = var('traffic_gold_shadow_schema', 'traffic_gold_candidate') %}
{% set model_name = var('traffic_gold_parity_model', 'gold_traffic_flow_link_latest') %}
{% set grain_columns = var('traffic_gold_parity_grain_columns', ['link_id']) %}

with old_relation as (
    select * from {{ target.database }}.{{ old_schema }}.{{ model_name }}
),

shadow_relation as (
    select * from {{ target.database }}.{{ shadow_schema }}.{{ model_name }}
),

old_minus_shadow as (
    select 'old_minus_shadow' as failure_reason, count(*) as failure_count
    from (
        select * from old_relation
        except
        select * from shadow_relation
    )
),

shadow_minus_old as (
    select 'shadow_minus_old' as failure_reason, count(*) as failure_count
    from (
        select * from shadow_relation
        except
        select * from old_relation
    )
),

shadow_duplicate_grain as (
    select 'shadow_duplicate_grain' as failure_reason, count(*) as failure_count
    from (
        select
            {% for column_name in grain_columns %}
            {{ column_name }}{% if not loop.last %},{% endif %}
            {% endfor %}
        from shadow_relation
        group by
            {% for column_name in grain_columns %}
            {{ column_name }}{% if not loop.last %},{% endif %}
            {% endfor %}
        having count(*) > 1
    )
),

row_count_delta as (
    select
        'row_count_delta' as failure_reason,
        abs(
            (select count(*) from old_relation)
            - (select count(*) from shadow_relation)
        ) as failure_count
)

select *
from old_minus_shadow
where failure_count <> 0
union all
select *
from shadow_minus_old
where failure_count <> 0
union all
select *
from shadow_duplicate_grain
where failure_count <> 0
union all
select *
from row_count_delta
where failure_count <> 0
