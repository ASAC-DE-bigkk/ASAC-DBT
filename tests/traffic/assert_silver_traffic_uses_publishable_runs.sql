select silver.dag_run_id
from {{ ref('silver_seoul_traffic_incident') }} as silver
left join {{ source('traffic_bronze', 'collection_run_manifest') }} as manifest
    on silver.dag_run_id = cast(manifest.dag_run_id as varchar)
    and manifest.source_id = 'seoul_traffic_incident'
    and manifest.status = 'SUCCESS'
    and manifest.is_publishable
where manifest.dag_run_id is null
limit 1
