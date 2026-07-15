select dag_run_id, raw_object_key, page_no, source_item_key
from {{ ref('silver_kma_vilage_fcst_observation') }}
group by 1, 2, 3, 4
having count(*) > 1
    or count_if(dag_run_id is null or raw_object_key is null or page_no is null or source_item_key is null) > 0
