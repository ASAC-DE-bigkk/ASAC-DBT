with invalid_interval as (
    select source_admin_code, bridge_version, nx, ny
    from {{ ref('bridge_weather_admin_dong_grid') }}
    where valid_from_at is not null and valid_to_at is not null
      and valid_from_at >= valid_to_at
),
overlap as (
    select left_side.source_admin_code, left_side.bridge_version, left_side.nx, left_side.ny
    from {{ ref('bridge_weather_admin_dong_grid') }} left_side
    join {{ ref('bridge_weather_admin_dong_grid') }} right_side
      on left_side.source_admin_code = right_side.source_admin_code
     and left_side.nx = right_side.nx
     and left_side.ny = right_side.ny
     and left_side.bridge_version < right_side.bridge_version
     and left_side.valid_from_at < coalesce(right_side.valid_to_at, timestamp '9999-12-31 00:00:00')
     and right_side.valid_from_at < coalesce(left_side.valid_to_at, timestamp '9999-12-31 00:00:00')
    where left_side.valid_from_at is not null and right_side.valid_from_at is not null
)
select * from invalid_interval
union all
select * from overlap
