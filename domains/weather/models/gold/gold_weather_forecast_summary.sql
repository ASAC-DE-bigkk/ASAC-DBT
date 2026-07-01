select
    source_id,
    count(*) as row_count,
    count(distinct raw_object_key) as raw_object_count,
    min(forecast_at) as first_forecast_at,
    max(forecast_at) as last_forecast_at,
    max(collected_at) as last_collected_at
from {{ ref('silver_kma_vilage_fcst') }}
group by source_id
