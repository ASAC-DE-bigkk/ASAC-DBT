-- depends_on: {{ ref('silver_seoul_traffic_incident_current') }}
-- depends_on: {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}
-- depends_on: {{ ref('asac_axes', 'dim_admin_dong') }}

with canonical as (
    select cast(admin_dong_code as varchar) as admin_dong_code
    from {{ ref('asac_axes', 'dim_admin_dong') }}
),

current_rows as (
    select
        cast(source_record_id as varchar) as source_record_id,
        cast(admin_dong_code as varchar) as admin_dong_code
    from {{ ref('silver_seoul_traffic_incident_current') }}
),

current_mapping as (
    select
        current.source_record_id,
        current.admin_dong_code as candidate_admin_dong_code,
        canonical.admin_dong_code as canonical_admin_dong_code
    from current_rows as current
    left join canonical
        on current.admin_dong_code = canonical.admin_dong_code
),

mapping_cardinality as (
    select
        source_record_id,
        candidate_admin_dong_code,
        count(canonical_admin_dong_code) as canonical_match_count
    from current_mapping
    group by source_record_id, candidate_admin_dong_code
),

complete_hours as (
    select distinct cast(hour_at as timestamp(6)) as hour_at
    from {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}
    where quality_state in ('complete', 'complete_zero')
),

expected_counts as (
    select
        canonical.admin_dong_code,
        complete_hours.hour_at,
        count(current.source_record_id) as incident_count
    from canonical
    cross join complete_hours
    left join current_rows as current
        on canonical.admin_dong_code = current.admin_dong_code
    group by canonical.admin_dong_code, complete_hours.hour_at
),

actual_counts as (
    select
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(hour_at as timestamp(6)) as hour_at,
        cast(incident_count as bigint) as incident_count
    from {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}
    where quality_state in ('complete', 'complete_zero')
),

missing_counts as (
    select * from expected_counts
    except
    select * from actual_counts
),

extra_counts as (
    select * from actual_counts
    except
    select * from expected_counts
)

select
    'current_to_canonical_fanout' as violation_type,
    candidate_admin_dong_code as admin_dong_code,
    cast(null as timestamp(6)) as hour_at,
    source_record_id,
    canonical_match_count as expected_count,
    cast(null as bigint) as actual_count
from mapping_cardinality
where canonical_match_count > 1

union all

select
    'missing_published_count' as violation_type,
    admin_dong_code,
    hour_at,
    cast(null as varchar) as source_record_id,
    incident_count as expected_count,
    cast(null as bigint) as actual_count
from missing_counts

union all

select
    'extra_published_count' as violation_type,
    admin_dong_code,
    hour_at,
    cast(null as varchar) as source_record_id,
    cast(null as bigint) as expected_count,
    incident_count as actual_count
from extra_counts
