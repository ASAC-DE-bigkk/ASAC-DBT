select silver.dag_run_id
from {{ ref('silver_kma_vilage_fcst') }} as silver
left join {{ source('weather_bronze', 'collection_run_manifest') }} as manifest
    on silver.dag_run_id = cast(manifest.dag_run_id as varchar)
    and manifest.source_id = 'kma_vilage_fcst'
    and manifest.status = 'SUCCESS'
    and manifest.is_publishable
where manifest.dag_run_id is null
limit 1
