-- depends_on: {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}
-- depends_on: {{ ref('asac_axes', 'dim_admin_dong') }}

with canonical as (
    select cast(admin_dong_code as varchar) as admin_dong_code
    from {{ ref('asac_axes', 'dim_admin_dong') }}
),

target_hours as (
    select distinct cast(hour_at as timestamp(6)) as hour_at
    from {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}
),

expected_cells as (
    select canonical.admin_dong_code, target_hours.hour_at
    from canonical
    cross join target_hours
),

actual_cells as (
    select
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(hour_at as timestamp(6)) as hour_at
    from {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}
),

missing_cells as (
    select * from expected_cells
    except
    select * from actual_cells
),

extra_cells as (
    select * from actual_cells
    except
    select * from expected_cells
),

scaffold_summary as (
    select
        (select count(*) from canonical) as canonical_row_count,
        (select count(distinct admin_dong_code) from canonical) as canonical_code_count,
        (select count_if(admin_dong_code is null) from canonical) as canonical_null_code_count,
        (select count(*) from target_hours) as target_hour_count,
        (select count(*) from actual_cells) as actual_cell_count,
        (select count_if(hour_at is null) from actual_cells) as null_hour_count
)

select
    'missing_target_cell' as violation_type,
    admin_dong_code,
    hour_at
from missing_cells

union all

select
    'extra_target_cell' as violation_type,
    admin_dong_code,
    hour_at
from extra_cells

union all

select
    'invalid_hourly_scaffold' as violation_type,
    cast(null as varchar) as admin_dong_code,
    cast(null as timestamp(6)) as hour_at
from scaffold_summary
where canonical_row_count = 0
   or canonical_row_count <> canonical_code_count
   or canonical_null_code_count <> 0
   or target_hour_count <> 1
   or actual_cell_count <> canonical_row_count
   or null_hour_count <> 0
