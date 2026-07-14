select 'gold_weather_forecast_summary_empty' as failure_reason
where not exists (
    select 1
    from {{ ref('gold_weather_forecast_summary') }}
)

union all

select concat('non_positive_counts:', source_id) as failure_reason
from {{ ref('gold_weather_forecast_summary') }}
where row_count <= 0
   or raw_object_count <= 0
