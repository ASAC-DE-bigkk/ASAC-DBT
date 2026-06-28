select *
from {{ ref('gold_ask_seoul_api_ingestion_summary') }}
where row_count <= 0
