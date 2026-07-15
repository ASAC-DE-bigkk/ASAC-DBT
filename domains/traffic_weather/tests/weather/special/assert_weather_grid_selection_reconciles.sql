{% if weather_w2_is_repair() %}
with eligible_manifest_anchors as (
    {{ weather_w2_latest_publishable_anchors_sql() }}
),

ranked_repair_candidates as (
    select
        observation.*,
        row_number() over (
            partition by observation.nx, observation.ny, observation.issued_at,
                         observation.forecast_at, observation.category
            order by
                observation.collected_at desc,
                observation.raw_object_key desc,
                observation.request_id desc,
                observation.dag_run_id desc,
                observation.page_no desc,
                observation.source_item_key desc
        ) as row_num
    from {{ ref('silver_kma_vilage_fcst_observation') }} as observation
    inner join eligible_manifest_anchors as anchor
        on observation.source_id = anchor.anchor_source_id
       and observation.dag_run_id = anchor.anchor_dag_run_id
    where observation.grid_eligibility_state = 'eligible'
      and observation.published_at >= timestamp '{{ weather_w2_repair_start_at() }}'
      and observation.published_at <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
),

expected as (
    select
        nx,
        ny,
        issued_at,
        forecast_at,
        category,
        source_id,
        dag_run_id as selected_dag_run_id,
        raw_object_key,
        page_no as selected_page_no,
        source_item_key as selected_source_item_key,
        request_id,
        collected_at,
        published_at,
        fcst_value_raw,
        try_cast(fcst_value_raw as double) as fcst_value_num,
        {{ kma_value_semantics('category', 'fcst_value_raw') }},
        date_diff('hour', issued_at, forecast_at) as forecast_lead_hours
    from ranked_repair_candidates
    where row_num = 1
),

actual as (
    select
        nx,
        ny,
        issued_at,
        forecast_at,
        category,
        source_id,
        selected_dag_run_id,
        raw_object_key,
        selected_page_no,
        selected_source_item_key,
        request_id,
        collected_at,
        published_at,
        fcst_value_raw,
        fcst_value_num,
        value_representation,
        value_num,
        value_lower_bound,
        value_upper_bound,
        qualitative_code,
        forecast_lead_hours
    from {{ ref('silver_kma_vilage_fcst_grid') }}
)

select
    expected.nx,
    expected.ny,
    expected.issued_at,
    expected.forecast_at,
    expected.category,
    expected.selected_dag_run_id as expected_dag_run_id,
    actual.selected_dag_run_id as actual_dag_run_id
from expected
left join actual
    on expected.nx = actual.nx
   and expected.ny = actual.ny
   and expected.issued_at = actual.issued_at
   and expected.forecast_at = actual.forecast_at
   and expected.category = actual.category
where actual.nx is null
   or not {{ weather_w2_grid_winner_is_newer('actual', 'expected') }}
   or (
       {{ weather_w2_grid_winner_is_newer('actual', 'expected') }}
       and not {{ weather_w2_grid_winner_is_newer('expected', 'actual') }}
       and actual.published_at >= timestamp '{{ weather_w2_repair_start_at() }}'
       and actual.published_at <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
       and not exists (
           select 1
           from eligible_manifest_anchors as anchor
           where anchor.anchor_source_id = actual.source_id
             and anchor.anchor_dag_run_id = actual.selected_dag_run_id
       )
   )
   or (
       {{ weather_w2_grid_winner_is_newer('expected', 'actual') }}
       and (
           actual.source_id is distinct from expected.source_id
           or actual.selected_dag_run_id is distinct from expected.selected_dag_run_id
           or actual.raw_object_key is distinct from expected.raw_object_key
           or actual.selected_page_no is distinct from expected.selected_page_no
           or actual.selected_source_item_key is distinct from expected.selected_source_item_key
           or actual.request_id is distinct from expected.request_id
           or actual.collected_at is distinct from expected.collected_at
           or actual.published_at is distinct from expected.published_at
           or actual.fcst_value_raw is distinct from expected.fcst_value_raw
           or actual.fcst_value_num is distinct from expected.fcst_value_num
           or actual.value_representation is distinct from expected.value_representation
           or actual.value_num is distinct from expected.value_num
           or actual.value_lower_bound is distinct from expected.value_lower_bound
           or actual.value_upper_bound is distinct from expected.value_upper_bound
           or actual.qualitative_code is distinct from expected.qualitative_code
           or actual.forecast_lead_hours is distinct from expected.forecast_lead_hours
       )
   )
{% else %}
with selected as (
    select *
    from (
        select *, row_number() over (
            partition by nx, ny, issued_at, forecast_at, category
            order by collected_at desc, raw_object_key desc, request_id desc, dag_run_id desc, page_no desc, source_item_key desc
        ) as row_num
        from {{ ref('silver_kma_vilage_fcst_observation') }}
        where nx > 0 and ny > 0 and category is not null
          and issued_at is not null and forecast_at is not null and time_parse_state = 'valid'
    )
    where row_num = 1
),
expected as (
    select
        nx, ny, issued_at, forecast_at, category,
        dag_run_id, raw_object_key, page_no, source_item_key,
        fcst_value_raw,
        try_cast(fcst_value_raw as double) as fcst_value_num,
        {{ kma_value_semantics('category', 'fcst_value_raw') }},
        date_diff('hour', issued_at, forecast_at) as forecast_lead_hours
    from selected
),
actual as (
    select
        nx, ny, issued_at, forecast_at, category,
        selected_dag_run_id as dag_run_id,
        selected_raw_object_key as raw_object_key,
        selected_page_no as page_no,
        selected_source_item_key as source_item_key,
        fcst_value_raw, fcst_value_num, value_representation, value_num,
        value_lower_bound, value_upper_bound, qualitative_code, forecast_lead_hours
    from {{ ref('silver_kma_vilage_fcst_grid') }}
),
missing as (select * from expected except select * from actual),
extra as (select * from actual except select * from expected)
select * from missing
union all
select * from extra
{% endif %}
