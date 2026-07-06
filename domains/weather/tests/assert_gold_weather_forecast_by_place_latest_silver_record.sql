with place_grid as (
    select
        place_id,
        nx,
        ny
    from {{ ref('dim_weather_place') }}
),

ranked_silver as (
    select
        nx,
        ny,
        category,
        forecast_at,
        issued_at,
        request_id,
        raw_object_key,
        collected_at,
        row_number() over (
            partition by nx, ny, forecast_at, category
            order by
                issued_at desc,
                collected_at desc,
                raw_object_key desc,
                request_id desc
        ) as row_num
    from {{ ref('silver_kma_vilage_fcst') }}
),

expected_gold as (
    select
        place_grid.place_id,
        ranked_silver.category,
        ranked_silver.forecast_at,
        ranked_silver.issued_at,
        ranked_silver.request_id,
        ranked_silver.raw_object_key,
        ranked_silver.collected_at
    from ranked_silver
    inner join place_grid
        on ranked_silver.nx = place_grid.nx
       and ranked_silver.ny = place_grid.ny
    where ranked_silver.row_num = 1
)

select
    expected_gold.place_id,
    expected_gold.forecast_at,
    expected_gold.category,
    gold.request_id as gold_request_id,
    expected_gold.request_id as expected_request_id,
    gold.raw_object_key as gold_raw_object_key,
    expected_gold.raw_object_key as expected_raw_object_key,
    gold.issued_at as gold_issued_at,
    expected_gold.issued_at as expected_issued_at,
    gold.collected_at as gold_collected_at,
    expected_gold.collected_at as expected_collected_at
from expected_gold
left join {{ ref('gold_weather_forecast_by_place') }} as gold
    on expected_gold.place_id = gold.place_id
   and expected_gold.forecast_at = gold.forecast_at
   and expected_gold.category = gold.category
where gold.place_id is null
   or gold.request_id is distinct from expected_gold.request_id
   or gold.raw_object_key is distinct from expected_gold.raw_object_key
   or gold.issued_at is distinct from expected_gold.issued_at
   or gold.collected_at is distinct from expected_gold.collected_at
