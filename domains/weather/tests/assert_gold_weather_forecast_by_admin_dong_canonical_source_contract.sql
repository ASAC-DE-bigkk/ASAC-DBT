-- depends_on: {{ ref('gold_weather_forecast_by_admin_dong') }}
-- depends_on: {{ ref('bridge_weather_admin_dong_grid') }}
-- depends_on: {{ ref('asac_axes', 'dim_admin_dong') }}

{% set canonical_contract = weather_w2_canonical_contract() %}

with canonical as (
    select
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(admin_dong as varchar) as admin_dong,
        cast(gu_code as varchar) as gu_code,
        cast(gu as varchar) as gu,
        cast(revision_date as date) as revision_date
    from {{ ref('asac_axes', 'dim_admin_dong') }}
    where cast(revision_date as date) = date '{{ canonical_contract['revision_date'] }}'
),

active_bridge as (
    select
        cast(source_admin_code as varchar) as source_admin_code,
        cast(bridge_version as varchar) as bridge_version,
        cast(nx as integer) as nx,
        cast(ny as integer) as ny
    from {{ ref('bridge_weather_admin_dong_grid') }}
    where cast(bridge_version as varchar) = 'weather_admin_dong_grid_bridge_v1'
),

mapped_canonical as (
    select active_bridge.source_admin_code
    from active_bridge
    inner join canonical
        on active_bridge.source_admin_code = canonical.admin_dong_code
),

contract_summary as (
    select
        (select count(*) from active_bridge) as bridge_row_count,
        (select count(distinct source_admin_code) from active_bridge) as bridge_code_count,
        (
            select count_if(
                source_admin_code is null
                or bridge_version is null
                or nx is null
                or ny is null
            )
            from active_bridge
        ) as bridge_null_count,
        (select count(*) from canonical) as canonical_row_count,
        (select count(distinct admin_dong_code) from canonical) as canonical_code_count,
        (select count(distinct revision_date) from canonical) as canonical_revision_count,
        (select min(revision_date) from canonical) as min_canonical_revision,
        (select max(revision_date) from canonical) as max_canonical_revision,
        (
            select count_if(
                admin_dong_code is null
                or admin_dong is null
                or gu_code is null
                or gu is null
                or revision_date is null
            )
            from canonical
        ) as canonical_null_count,
        (select count(*) from mapped_canonical) as mapped_canonical_row_count,
        (
            select count(distinct source_admin_code)
            from mapped_canonical
        ) as mapped_canonical_code_count
)

select *
from contract_summary
where bridge_row_count <> {{ canonical_contract['bridge_count'] }}
   or bridge_code_count <> {{ canonical_contract['bridge_count'] }}
   or bridge_null_count <> 0
   or canonical_row_count <> {{ canonical_contract['canonical_count'] }}
   or canonical_code_count <> {{ canonical_contract['canonical_count'] }}
   or canonical_revision_count <> 1
   or min_canonical_revision is distinct from date '{{ canonical_contract['revision_date'] }}'
   or max_canonical_revision is distinct from date '{{ canonical_contract['revision_date'] }}'
   or canonical_null_count <> 0
   or mapped_canonical_row_count <> {{ canonical_contract['mapped_canonical_count'] }}
   or mapped_canonical_code_count <> {{ canonical_contract['mapped_canonical_count'] }}
