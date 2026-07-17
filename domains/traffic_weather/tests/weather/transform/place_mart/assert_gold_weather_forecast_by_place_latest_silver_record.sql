-- Preserve the full-history winner order without a global row_number/TopN plan.
-- Exact ties are equivalent because every projected lineage field is part of the key.
with latest_silver as (
    select
        place_id,
        category,
        forecast_at,
        max_by(
            cast(row(
                cast(issued_at as timestamp(6)),
                cast(request_id as varchar),
                cast(raw_object_key as varchar),
                cast(collected_at as timestamp(6))
            ) as row(
                issued_at timestamp(6),
                request_id varchar,
                raw_object_key varchar,
                collected_at timestamp(6)
            )),
            row(
                cast(issued_at is not null as tinyint),
                cast(issued_at as timestamp(6)),
                cast(collected_at is not null as tinyint),
                cast(collected_at as timestamp(6)),
                cast(raw_object_key is not null as tinyint),
                cast(raw_object_key as varchar),
                cast(request_id is not null as tinyint),
                cast(request_id as varchar)
            )
        ) as latest_record
    from {{ ref('silver_weather_forecast_by_admin_dong') }}
    group by place_id, forecast_at, category
),

expected_gold as (
    select
        place_id,
        category,
        forecast_at,
        latest_record.issued_at as issued_at,
        latest_record.request_id as request_id,
        latest_record.raw_object_key as raw_object_key,
        latest_record.collected_at as collected_at
    from latest_silver
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
