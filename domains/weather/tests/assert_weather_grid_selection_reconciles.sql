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
