with core_categories(category) as (
    values
        ('TMP'),
        ('REH'),
        ('WSD'),
        ('POP'),
        ('SKY'),
        ('PTY'),
        ('PCP'),
        ('SNO')
),

core_summary as (
    select count(*) as core_category_count
    from core_categories
),

mapped_bridge as (
    select distinct
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(nx as integer) as nx,
        cast(ny as integer) as ny
    from {{ ref('bridge_weather_admin_dong_grid') }}
    where cast(bridge_version as varchar) = 'weather_admin_dong_grid_bridge_v1'
      and canonical_join_eligible = true
      and admin_dong_code is not null
),

mapped_admin_universe as (
    select distinct admin_dong_code
    from mapped_bridge
),

bridge_summary as (
    select count(*) as mapped_admin_dong_count
    from mapped_admin_universe
),

grid_core as (
    select
        cast(nx as integer) as nx,
        cast(ny as integer) as ny,
        cast(issued_at as timestamp(6)) as issued_at,
        cast(forecast_at as timestamp(6)) as forecast_at,
        date(cast(forecast_at as timestamp(6))) as forecast_date,
        cast(category as varchar) as category,
        cast(collected_at as timestamp(6)) as collected_at,
        cast(published_at as timestamp(6)) as published_at
    from {{ ref('silver_kma_vilage_fcst_grid') }}
    where category in ('TMP', 'REH', 'WSD', 'POP', 'SKY', 'PTY', 'PCP', 'SNO')
),

forecast_slots as (
    select
        issued_at,
        forecast_date,
        count(distinct forecast_at) as forecast_slot_count
    from grid_core
    group by issued_at, forecast_date
),

observed_cell_keys as (
    select distinct
        grid_core.issued_at,
        grid_core.forecast_date,
        grid_core.forecast_at,
        mapped_bridge.admin_dong_code,
        grid_core.category
    from grid_core
    inner join mapped_bridge
        on grid_core.nx = mapped_bridge.nx
       and grid_core.ny = mapped_bridge.ny
),

observed_agg as (
    select
        issued_at,
        forecast_date,
        count(*) as observed_cell_count
    from observed_cell_keys
    group by issued_at, forecast_date
),

lineage_agg as (
    select
        issued_at,
        forecast_date,
        max(collected_at) as weather_collected_at_max,
        max(published_at) as weather_published_at_max
    from grid_core
    group by issued_at, forecast_date
),

scored as (
    select
        forecast_slots.issued_at,
        forecast_slots.forecast_date,
        forecast_slots.forecast_slot_count,
        bridge_summary.mapped_admin_dong_count,
        forecast_slots.forecast_slot_count * bridge_summary.mapped_admin_dong_count * core_summary.core_category_count as expected_cell_count,
        coalesce(observed_agg.observed_cell_count, 0) as observed_cell_count,
        lineage_agg.weather_collected_at_max,
        lineage_agg.weather_published_at_max
    from forecast_slots
    cross join bridge_summary
    cross join core_summary
    left join observed_agg
        on forecast_slots.issued_at = observed_agg.issued_at
       and forecast_slots.forecast_date = observed_agg.forecast_date
    left join lineage_agg
        on forecast_slots.issued_at = lineage_agg.issued_at
       and forecast_slots.forecast_date = lineage_agg.forecast_date
)

select
    concat(to_iso8601(cast(scored.issued_at as timestamp(6))), '|', cast(scored.forecast_date as varchar)) as product_row_id,
    scored.issued_at,
    scored.forecast_date,
    scored.forecast_slot_count,
    scored.mapped_admin_dong_count,
    scored.expected_cell_count,
    scored.observed_cell_count,
    scored.expected_cell_count - scored.observed_cell_count as missing_cell_count,
    case
        when scored.expected_cell_count = 0 then cast(null as double)
        else cast(scored.observed_cell_count as double) / scored.expected_cell_count
    end as issue_cycle_coverage_ratio,
    case
        when scored.mapped_admin_dong_count <> 425 then 'bridge_contract_mismatch'
        when scored.observed_cell_count = scored.expected_cell_count then 'complete'
        when scored.observed_cell_count = 0 then 'missing'
        else 'partial'
    end as issue_cycle_coverage_state,
    scored.weather_collected_at_max,
    scored.weather_published_at_max
from scored
