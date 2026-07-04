select
    place_id,
    nx,
    ny
from {{ ref('weather_place_grid_mapping') }}
where nx < 56
   or nx > 65
   or ny < 123
   or ny > 130
