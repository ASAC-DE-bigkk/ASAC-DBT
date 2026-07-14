select
    grid.selected_dag_run_id,
    grid.selected_raw_object_key,
    grid.selected_page_no,
    grid.selected_source_item_key
from {{ ref('silver_kma_vilage_fcst_grid') }} grid
left join {{ ref('silver_kma_vilage_fcst_observation') }} observation
  on grid.selected_dag_run_id = observation.dag_run_id
 and grid.selected_raw_object_key = observation.raw_object_key
 and grid.selected_page_no = observation.page_no
 and grid.selected_source_item_key = observation.source_item_key
where observation.source_item_key is null
