with legacy as (
    select cast(place_id as varchar) as place_id,
           cast(source_admin_code as varchar) as source_admin_code,
           cast(nx as integer) as nx,
           cast(ny as integer) as ny
    from {{ ref('weather_place_grid_mapping') }}
),
bridge as (
    select place_id, source_admin_code, nx, ny
    from {{ ref('bridge_weather_admin_dong_grid') }}
    where bridge_version = 'weather_admin_dong_grid_bridge_v1'
),
missing as (select * from legacy except select * from bridge),
extra as (select * from bridge except select * from legacy)
select * from missing
union all
select * from extra
