select source_admin_code, bridge_version, nx, ny
from {{ ref('bridge_weather_admin_dong_grid') }}
group by 1, 2, 3, 4
having count(*) > 1
    or count_if(source_admin_code is null or bridge_version is null or nx is null or ny is null) > 0
