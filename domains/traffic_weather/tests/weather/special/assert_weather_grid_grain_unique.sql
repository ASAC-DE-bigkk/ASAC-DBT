select nx, ny, issued_at, forecast_at, category
from {{ ref('silver_kma_vilage_fcst_grid') }}
group by 1, 2, 3, 4, 5
having count(*) > 1
    or count_if(nx is null or ny is null or issued_at is null or forecast_at is null or category is null) > 0
