with latest_issued_at as (
    select max(issued_at) as issued_at
    from {{ ref('silver_kma_vilage_fcst') }}
),

coverage as (
    select
        count(distinct concat(cast(nx as varchar), ':', cast(ny as varchar))) as grid_count
    from {{ ref('silver_kma_vilage_fcst') }}
    where issued_at = (select issued_at from latest_issued_at)
)

select
    grid_count,
    {{ env_var('ASK_SEOUL_REPORT_EXPECTED_KMA_GRIDS', '80') | int }} as expected_grid_count
from coverage
where grid_count < {{ env_var('ASK_SEOUL_REPORT_EXPECTED_KMA_GRIDS', '80') | int }}
