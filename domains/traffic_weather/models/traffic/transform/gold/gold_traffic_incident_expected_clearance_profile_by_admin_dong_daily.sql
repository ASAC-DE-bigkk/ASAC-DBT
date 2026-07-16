-- Expected-clearance evidence among incidents present in the pinned current snapshot.
-- Lead minutes are source-provided expectations, not observed resolution duration.
-- depends_on: {{ ref('silver_seoul_traffic_incident_current') }}
-- depends_on: {{ ref('asac_axes', 'dim_admin_dong') }}

{{ config(materialized='table') }}

with canonical_raw as (
    select
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(admin_dong as varchar) as admin_dong,
        cast(gu_code as varchar) as gu_code,
        cast(gu as varchar) as gu,
        try_cast(revision_date as date) as admin_dong_revision_date
    from {{ ref('asac_axes', 'dim_admin_dong') }}
),

canonical_ranked as (
    select
        *,
        row_number() over (
            partition by admin_dong_code
            order by
                admin_dong_revision_date desc nulls last,
                admin_dong asc nulls last,
                gu_code asc nulls last,
                gu asc nulls last
        ) as canonical_row_num
    from canonical_raw
),

canonical as (
    select *
    from canonical_ranked
    where admin_dong_code is not null
      and canonical_row_num = 1
),

classified as (
    select
        cast(current_snapshot.occurred_at as date) as profile_day,
        coalesce(canonical.admin_dong_code, '__UNMAPPED__') as mapping_bucket,
        canonical.admin_dong_code,
        canonical.admin_dong,
        canonical.gu_code,
        canonical.gu,
        canonical.admin_dong_revision_date,
        cast(current_snapshot.dag_run_id as varchar) as snapshot_dag_run_id,
        cast(current_snapshot.occurred_at as timestamp(6)) as occurred_at,
        cast(current_snapshot.expected_clear_at as timestamp(6))
            as expected_clear_at,
        case
            when current_snapshot.expected_clear_at
                >= current_snapshot.occurred_at
                then date_diff(
                    'minute',
                    current_snapshot.occurred_at,
                    current_snapshot.expected_clear_at
                )
        end as expected_clearance_lead_minutes
    from {{ ref('silver_seoul_traffic_incident_current') }} as current_snapshot
    left join canonical
        on cast(current_snapshot.admin_dong_code as varchar)
            = canonical.admin_dong_code
    where current_snapshot.occurred_at is not null
),

profile_evidence as (
    select
        profile_day,
        mapping_bucket,
        admin_dong_code,
        admin_dong,
        gu_code,
        gu,
        admin_dong_revision_date,
        max(snapshot_dag_run_id) as snapshot_dag_run_id,
        count(distinct snapshot_dag_run_id) as snapshot_run_count,
        count(*) as incident_count,
        count_if(expected_clear_at is not null)
            as expected_clearance_present_count,
        count_if(expected_clear_at is null)
            as expected_clearance_missing_count,
        count_if(expected_clear_at >= occurred_at)
            as expected_clearance_usable_count,
        count_if(expected_clear_at < occurred_at)
            as expected_clearance_invalid_count,
        min(expected_clearance_lead_minutes)
            as min_expected_clearance_lead_minutes,
        avg(cast(expected_clearance_lead_minutes as double))
            as avg_expected_clearance_lead_minutes,
        max(expected_clearance_lead_minutes)
            as max_expected_clearance_lead_minutes
    from classified
    group by
        profile_day,
        mapping_bucket,
        admin_dong_code,
        admin_dong,
        gu_code,
        gu,
        admin_dong_revision_date
)

select
    concat(cast(profile_day as varchar), '|', mapping_bucket)
        as product_row_id,
    profile_day,
    mapping_bucket,
    admin_dong_code,
    admin_dong,
    gu_code,
    gu,
    admin_dong_revision_date,
    snapshot_dag_run_id,
    snapshot_run_count,
    cast('pinned_current_snapshot_by_occurrence_day' as varchar)
        as evidence_scope,
    incident_count,
    expected_clearance_present_count,
    expected_clearance_missing_count,
    expected_clearance_usable_count,
    expected_clearance_invalid_count,
    cast(expected_clearance_present_count as double)
        / cast(incident_count as double)
        as expected_clearance_present_ratio,
    cast(expected_clearance_missing_count as double)
        / cast(incident_count as double)
        as expected_clearance_missing_ratio,
    cast(expected_clearance_usable_count as double)
        / cast(incident_count as double)
        as expected_clearance_usable_ratio,
    cast(expected_clearance_invalid_count as double)
        / cast(incident_count as double)
        as expected_clearance_invalid_ratio,
    min_expected_clearance_lead_minutes,
    avg_expected_clearance_lead_minutes,
    max_expected_clearance_lead_minutes,
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
    end as profile_state
from profile_evidence
