-- depends_on: {{ ref('gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily') }}

{% set snapshot_dag_run_id = var('traffic_snapshot_dag_run_id') %}

with checked as (
    select
        *,
        count(*) over (
            partition by profile_day, mapping_bucket
        ) as natural_grain_row_count,
        count(*) over (
            partition by product_row_id
        ) as product_row_id_row_count,
        case
            when expected_clearance_present_count = 0
                then 'no_expected_clearance_evidence'
            when expected_clearance_usable_count = 0
             and expected_clearance_invalid_count > 0
                then 'invalid_expected_clearance_evidence'
            when expected_clearance_missing_count > 0
              or expected_clearance_invalid_count > 0
                then 'partial_expected_clearance_evidence'
            else 'complete_expected_clearance_evidence'
        end as expected_profile_state
    from {{ ref('gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily') }}
)

select *
from checked
where product_row_id is null
   or profile_day is null
   or mapping_bucket is null
   or snapshot_dag_run_id is null
   or snapshot_dag_run_id is distinct from '{{ snapshot_dag_run_id | replace("'", "''") }}'
   or snapshot_run_count <> 1
   or evidence_scope is distinct from 'pinned_current_snapshot_by_occurrence_day'
   or natural_grain_row_count <> 1
   or product_row_id_row_count <> 1
   or product_row_id is distinct from concat(
       cast(profile_day as varchar),
       '|',
       mapping_bucket
   )
   or incident_count <= 0
   or expected_clearance_present_count < 0
   or expected_clearance_missing_count < 0
   or expected_clearance_usable_count < 0
   or expected_clearance_invalid_count < 0
   or incident_count is distinct from (
       expected_clearance_present_count + expected_clearance_missing_count
   )
   or expected_clearance_present_count is distinct from (
       expected_clearance_usable_count + expected_clearance_invalid_count
   )
   or abs(
       expected_clearance_present_ratio
       - cast(expected_clearance_present_count as double)
         / cast(incident_count as double)
   ) > 0.000000000001
   or abs(
       expected_clearance_missing_ratio
       - cast(expected_clearance_missing_count as double)
         / cast(incident_count as double)
   ) > 0.000000000001
   or abs(
       expected_clearance_usable_ratio
       - cast(expected_clearance_usable_count as double)
         / cast(incident_count as double)
   ) > 0.000000000001
   or abs(
       expected_clearance_invalid_ratio
       - cast(expected_clearance_invalid_count as double)
         / cast(incident_count as double)
   ) > 0.000000000001
   or (
       expected_clearance_usable_count = 0
       and (
           min_expected_clearance_lead_minutes is not null
           or avg_expected_clearance_lead_minutes is not null
           or max_expected_clearance_lead_minutes is not null
       )
   )
   or (
       expected_clearance_usable_count > 0
       and (
           min_expected_clearance_lead_minutes is null
           or avg_expected_clearance_lead_minutes is null
           or max_expected_clearance_lead_minutes is null
           or min_expected_clearance_lead_minutes < 0
           or min_expected_clearance_lead_minutes
               > avg_expected_clearance_lead_minutes
           or avg_expected_clearance_lead_minutes
               > max_expected_clearance_lead_minutes
       )
   )
   or profile_state is distinct from expected_profile_state
   or (
       mapping_bucket = '__UNMAPPED__'
       and (
           admin_dong_code is not null
           or admin_dong is not null
           or gu_code is not null
           or gu is not null
           or admin_dong_revision_date is not null
       )
   )
   or (
       mapping_bucket <> '__UNMAPPED__'
       and (
           admin_dong_code is distinct from mapping_bucket
           or admin_dong is null
           or gu_code is null
           or gu is null
           or admin_dong_revision_date is null
       )
   )
