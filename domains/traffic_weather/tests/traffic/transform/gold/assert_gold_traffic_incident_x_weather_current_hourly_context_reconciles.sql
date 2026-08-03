{{ config(tags=['traffic_gold_gate']) }}

with weather_bridge as (
    select
        cast(source_admin_code as varchar) as admin_dong_code,
        cast(nx as integer) as nx,
        cast(ny as integer) as ny
    from {{ ref('bridge_weather_admin_dong_grid') }}
    where cast(bridge_version as varchar) = 'weather_admin_dong_grid_bridge_v1'
      and cast(canonical_join_eligible as boolean)
),

weather_history as (
    select
        cast(nx as integer) as nx,
        cast(ny as integer) as ny,
        cast(source_grid_place_id as varchar) as source_grid_place_id,
        cast(issued_at as timestamp(6)) as issued_at,
        cast(forecast_at as timestamp(6)) as forecast_at,
        cast(category as varchar) as category,
        cast(collected_at as timestamp(6)) as collected_at,
        cast(published_at as timestamp(6)) as published_at,
        cast(value_num as double) as value_num,
        cast(qualitative_code as varchar) as qualitative_code,
        cast(raw_object_key as varchar) as raw_object_key,
        cast(request_id as varchar) as request_id,
        cast(selected_dag_run_id as varchar) as dag_run_id
    from {{ ref('silver_kma_vilage_fcst_grid') }}
    where issued_at is not null
),

weather_candidates as (
    select
        traffic.product_row_id,
        lower(cast(weather.category as varchar)) as category,
        weather.issued_at,
        weather.collected_at,
        weather.published_at,
        weather.value_num,
        weather.qualitative_code,
        row_number() over (
            partition by traffic.product_row_id, lower(cast(weather.category as varchar))
            order by {{ weather_w2_grid_winner_order_key('weather') }} desc
        ) as category_row_num
    from {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }} as traffic
    inner join weather_bridge
        on cast(traffic.admin_dong_code as varchar) = weather_bridge.admin_dong_code
    inner join weather_history as weather
        on weather_bridge.nx = weather.nx
       and weather_bridge.ny = weather.ny
       and cast(date_trunc('hour', weather.forecast_at) as timestamp(6))
            = cast(traffic.hour_at as timestamp(6))
       and weather.issued_at <= cast(traffic.status_observed_at as timestamp(6))
    where lower(cast(weather.category as varchar)) in ('tmp', 'pop', 'reh', 'wsd', 'sky', 'pty')
),

latest_category as (
    select *
    from weather_candidates
    where category_row_num = 1
),

expected as (
    select
        product_row_id,
        count(distinct category) as weather_category_coverage_count,
        max(issued_at) as weather_latest_issued_at,
        max(collected_at) as weather_latest_collected_at,
        max(published_at) as weather_latest_published_at,
        max(case when category = 'tmp' then value_num end) as tmp_value_num,
        max(case when category = 'pop' then value_num end) as pop_value_num,
        max(case when category = 'reh' then value_num end) as reh_value_num,
        max(case when category = 'wsd' then value_num end) as wsd_value_num,
        max(case when category = 'sky' then qualitative_code end) as sky_qualitative_code,
        max(case when category = 'pty' then qualitative_code end) as pty_qualitative_code,
        case
            when count_if(category = 'pty') = 0 then cast(null as boolean)
            when max(case when category = 'pty' then qualitative_code end) = '0'
                then false
            when max(case when category = 'pty' then qualitative_code end)
                in ('1', '2', '3', '4', '5', '6', '7')
                then true
            else cast(null as boolean)
        end as is_precipitating
    from latest_category
    group by product_row_id
),

gold as (
    select
        product_row_id,
        weather_category_coverage_count,
        weather_latest_issued_at,
        weather_latest_collected_at,
        weather_latest_published_at,
        tmp_value_num,
        pop_value_num,
        reh_value_num,
        wsd_value_num,
        sky_qualitative_code,
        pty_qualitative_code,
        is_precipitating
    from {{ ref('gold_traffic_incident_x_weather_current_hourly') }}
    where weather_category_coverage_count is not null
)

select
    coalesce(gold.product_row_id, expected.product_row_id) as product_row_id
from gold
full outer join expected
    on gold.product_row_id = expected.product_row_id
where gold.product_row_id is null
   or expected.product_row_id is null
   or gold.weather_category_coverage_count
        is distinct from expected.weather_category_coverage_count
   or gold.weather_latest_issued_at is distinct from expected.weather_latest_issued_at
   or gold.weather_latest_collected_at
        is distinct from expected.weather_latest_collected_at
   or gold.weather_latest_published_at
        is distinct from expected.weather_latest_published_at
   or gold.tmp_value_num is distinct from expected.tmp_value_num
   or gold.pop_value_num is distinct from expected.pop_value_num
   or gold.reh_value_num is distinct from expected.reh_value_num
   or gold.wsd_value_num is distinct from expected.wsd_value_num
   or gold.sky_qualitative_code is distinct from expected.sky_qualitative_code
   or gold.pty_qualitative_code is distinct from expected.pty_qualitative_code
   or gold.is_precipitating is distinct from expected.is_precipitating
