-- depends_on: {{ ref('silver_seoul_traffic_incident_current') }}
-- depends_on: {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}

{% set snapshot_dag_run_id = var('traffic_snapshot_dag_run_id') %}

with gold_summary as (
    select
        count(*) as gold_row_count,
        count_if(
            cast(snapshot_dag_run_id as varchar)
                is distinct from '{{ snapshot_dag_run_id | replace("'", "''") }}'
        ) as gold_dag_run_mismatch_count,
        count(distinct quality_state) as quality_state_count,
        count_if(quality_state in ('complete', 'complete_zero')) as complete_row_count,
        coalesce(sum(incident_count), cast(0 as bigint)) as published_incident_count
    from {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}
),

current_summary as (
    select
        count(*) as current_incident_count,
        count_if(
            cast(dag_run_id as varchar)
                is distinct from '{{ snapshot_dag_run_id | replace("'", "''") }}'
        ) as current_dag_run_mismatch_count
    from {{ ref('silver_seoul_traffic_incident_current') }}
)

select *
from gold_summary
cross join current_summary
where gold_row_count = 0
   or gold_dag_run_mismatch_count > 0
   or current_dag_run_mismatch_count > 0
   or quality_state_count <> 1
   or (
       complete_row_count = gold_row_count
       and published_incident_count <> current_incident_count
   )
