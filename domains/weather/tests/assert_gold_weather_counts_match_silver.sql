with silver_counts as (
    select
        source_id,
        count(*) as row_count,
        count(distinct raw_object_key) as raw_object_count
    from {{ ref('silver_kma_vilage_fcst') }}
    group by source_id
),

gold_counts as (
    select
        source_id,
        row_count,
        raw_object_count
    from {{ ref('gold_weather_forecast_summary') }}
)

select
    coalesce(s.source_id, g.source_id) as source_id,
    s.row_count as silver_row_count,
    g.row_count as gold_row_count,
    s.raw_object_count as silver_raw_object_count,
    g.raw_object_count as gold_raw_object_count
from silver_counts s
full outer join gold_counts g
    on s.source_id = g.source_id
where coalesce(s.row_count, -1) != coalesce(g.row_count, -1)
   or coalesce(s.raw_object_count, -1) != coalesce(g.raw_object_count, -1)
