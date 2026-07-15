-- depends_on: {{ ref('gold_weather_forecast_by_admin_dong') }}

select
    admin_dong_code,
    forecast_at,
    category,
    product_row_id,
    concat(
        admin_dong_code,
        '|',
        to_iso8601(cast(forecast_at as timestamp(6))),
        '|',
        category
    ) as expected_product_row_id
from {{ ref('gold_weather_forecast_by_admin_dong') }}
where product_row_id is distinct from concat(
    admin_dong_code,
    '|',
    to_iso8601(cast(forecast_at as timestamp(6))),
    '|',
    category
)
