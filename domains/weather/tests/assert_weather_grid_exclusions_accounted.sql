with observation_state as (
    select
        dag_run_id,
        raw_object_key,
        page_no,
        source_item_key,
        case when nx > 0 and ny > 0 then 'valid' else 'invalid' end as expected_coordinate_state,
        case when category is not null then 'valid' else 'missing' end as expected_category_state,
        case when issued_at is not null and forecast_at is not null then 'valid' else 'invalid' end as expected_time_state,
        case
            when nx > 0 and ny > 0
             and category is not null
             and issued_at is not null
             and forecast_at is not null
            then 'eligible'
            else 'excluded'
        end as expected_eligibility_state,
        grid_coordinate_state,
        grid_category_state,
        grid_time_state,
        grid_eligibility_state
    from {{ ref('silver_kma_vilage_fcst_observation') }}
),
state_mismatch as (
    select dag_run_id, raw_object_key, page_no, source_item_key
    from observation_state
    where grid_coordinate_state is distinct from expected_coordinate_state
       or grid_category_state is distinct from expected_category_state
       or grid_time_state is distinct from expected_time_state
       or grid_eligibility_state is distinct from expected_eligibility_state
),
excluded_in_grid as (
    select
        observation.dag_run_id,
        observation.raw_object_key,
        observation.page_no,
        observation.source_item_key
    from observation_state observation
    join {{ ref('silver_kma_vilage_fcst_grid') }} grid
      on observation.dag_run_id = grid.selected_dag_run_id
     and observation.raw_object_key = grid.selected_raw_object_key
     and observation.page_no = grid.selected_page_no
     and observation.source_item_key = grid.selected_source_item_key
    where observation.grid_eligibility_state = 'excluded'
)
select * from state_mismatch
union all
select * from excluded_in_grid
