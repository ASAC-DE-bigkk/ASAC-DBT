with latest_issued_at as (
    select max(issued_at) as issued_at
    from {{ ref('gold_weather_forecast_by_place') }}
),

major_places as (
    select place_id
    from {{ ref('dim_weather_place') }}
    where strpos(concat('|', alias_names, '|'), '|홍대|') > 0
       or strpos(concat('|', alias_names, '|'), '|건대|') > 0
       or strpos(concat('|', alias_names, '|'), '|강남|') > 0
       or strpos(concat('|', alias_names, '|'), '|성수|') > 0
       or strpos(concat('|', alias_names, '|'), '|여의도|') > 0
),

coverage as (
    select
        major_places.place_id,
        count(forecast.place_id) as forecast_row_count
    from major_places
    left join {{ ref('gold_weather_forecast_by_place') }} as forecast
        on major_places.place_id = forecast.place_id
       and forecast.issued_at = (select issued_at from latest_issued_at)
    group by major_places.place_id
)

select *
from coverage
where forecast_row_count = 0
