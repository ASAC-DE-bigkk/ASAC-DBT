with expected_mapping_count as (
    select bridge_version, nx, ny, count(*) as mapping_count
    from {{ ref('weather_admin_dong_grid_bridge_history') }}
    group by 1, 2, 3
),
actual_mapping_count as (
    select bridge_version, nx, ny, count(*) as mapping_count
    from {{ ref('bridge_weather_admin_dong_grid') }}
    group by 1, 2, 3
),
mapping_missing as (
    select * from expected_mapping_count except select * from actual_mapping_count
),
mapping_extra as (
    select * from actual_mapping_count except select * from expected_mapping_count
),
expected_grid_fanout as (
    select
        grid.nx, grid.ny, grid.issued_at, grid.forecast_at, grid.category,
        seed.bridge_version, seed.source_admin_code,
        canonical.admin_dong_code
    from {{ ref('silver_kma_vilage_fcst_grid') }} grid
    join {{ ref('weather_admin_dong_grid_bridge_history') }} seed
      on grid.nx = seed.nx and grid.ny = seed.ny
    join {{ ref('asac_axes', 'dim_admin_dong') }} canonical
      on seed.source_admin_code = canonical.admin_dong_code
),
actual_grid_fanout as (
    select
        grid.nx, grid.ny, grid.issued_at, grid.forecast_at, grid.category,
        bridge.bridge_version, bridge.source_admin_code,
        bridge.admin_dong_code
    from {{ ref('silver_kma_vilage_fcst_grid') }} grid
    join {{ ref('bridge_weather_admin_dong_grid') }} bridge
      on grid.nx = bridge.nx and grid.ny = bridge.ny
    where bridge.canonical_join_eligible
),
fanout_missing as (
    select * from expected_grid_fanout except select * from actual_grid_fanout
),
fanout_extra as (
    select * from actual_grid_fanout except select * from expected_grid_fanout
)
select cast(bridge_version as varchar) as difference_key from mapping_missing
union all select cast(bridge_version as varchar) from mapping_extra
union all select concat(bridge_version, ':', source_admin_code) from fanout_missing
union all select concat(bridge_version, ':', source_admin_code) from fanout_extra
