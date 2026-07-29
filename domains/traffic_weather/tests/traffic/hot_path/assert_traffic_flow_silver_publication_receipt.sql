{% set flow_run_id = var('traffic_flow_snapshot_dag_run_id', '') or '' %}
{% set escaped_flow_run_id = flow_run_id | replace("'", "''") %}

with latest_manifest_state as (
    {{ latest_manifest_run_state('traffic_bronze', 'collection_run_manifest', 'seoul_traffic_flow') }}
),

configured_run as (
    select '{{ escaped_flow_run_id }}' as dag_run_id
),

pinned_run as (
    select manifest.dag_run_id
    from latest_manifest_state as manifest
    inner join configured_run
        on manifest.dag_run_id = configured_run.dag_run_id
    where manifest.manifest_status = 'SUCCESS'
      and manifest.is_publishable
),

missing_pinned_run as (
    select
        'missing_pinned_run' as violation_type,
        cast(null as varchar) as link_id
    from configured_run
    left join pinned_run using (dag_run_id)
    where pinned_run.dag_run_id is null
       or configured_run.dag_run_id = ''
       or not exists (
           select 1
           from {{ ref('silver_seoul_traffic_flow') }} as flow
           where cast(flow.dag_run_id as varchar) = configured_run.dag_run_id
       )
),

stale_or_mixed_flow_row as (
    select
        'stale_or_mixed_flow_row' as violation_type,
        cast(flow.link_id as varchar) as link_id
    from {{ ref('silver_seoul_traffic_flow') }} as flow
    cross join pinned_run
    where cast(flow.dag_run_id as varchar) = '{{ escaped_flow_run_id }}'
      and cast(flow.dag_run_id as varchar) is distinct from pinned_run.dag_run_id
),

invalid_critical_field as (
    select
        'invalid_critical_field' as violation_type,
        cast(link_id as varchar) as link_id
    from {{ ref('silver_seoul_traffic_flow') }}
    where cast(dag_run_id as varchar) = '{{ escaped_flow_run_id }}'
      and (
          link_id is null
          or source_id is null
          or observed_at is null
      )
),

duplicate_link_id as (
    select
        'duplicate_link_id' as violation_type,
        cast(link_id as varchar) as link_id
    from {{ ref('silver_seoul_traffic_flow') }}
    where cast(dag_run_id as varchar) = '{{ escaped_flow_run_id }}'
    group by link_id
    having count(*) > 1
)

select * from missing_pinned_run
union all
select * from stale_or_mixed_flow_row
union all
select * from invalid_critical_field
union all
select * from duplicate_link_id
