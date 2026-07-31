-- Traffic canonical current-hourly rows enriched with eligible KMA forecast context.
-- Grain: one row per Traffic product_row_id / admin_dong_code / hour_at.
-- Weather is context only; missing Weather evidence never removes or rewrites Traffic rows.
-- canonical_admin_dong: anchor가 이미 확정한 stamp를 재검증하는 방어적 join(신규 컬럼 없음,
-- public_gold space.enabled 계약의 "모델 직접 dim_admin_dong dependency" 요구사항 충족용).
-- depends_on: {{ ref('asac_axes', 'dim_admin_dong') }}

{{ config(materialized='table') }}

with canonical_admin_dong as (
    select distinct cast(admin_dong_code as varchar) as admin_dong_code
    from {{ ref('asac_axes', 'dim_admin_dong') }}
    where admin_dong_code is not null
),

traffic as (
    select
        product_row_id,
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(hour_at as timestamp(6)) as hour_at,
        cast(admin_dong as varchar) as admin_dong,
        cast(gu_code as varchar) as gu_code,
        cast(gu as varchar) as gu,
        cast(admin_dong_revision_date as date) as admin_dong_revision_date,
        cast(incident_count as bigint) as incident_count,
        cast(has_incident as boolean) as has_incident,
        cast(quality_state as varchar) as quality_state,
        cast(snapshot_as_of_at as timestamp(6)) as snapshot_as_of_at,
        cast(status_observed_at as timestamp(6)) as status_observed_at,
        cast(published_at as timestamp(6)) as published_at,
        cast(snapshot_dag_run_id as varchar) as snapshot_dag_run_id,
        cast(source_id as varchar) as source_id
    from {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}
),

weather_candidates as (
    select
        traffic.product_row_id as traffic_product_row_id,
        weather.category,
        cast(weather.issued_at as timestamp(6)) as issued_at,
        cast(weather.collected_at as timestamp(6)) as collected_at,
        cast(weather.published_at as timestamp(6)) as published_at,
        cast(weather.value_num as double) as value_num,
        cast(weather.qualitative_code as varchar) as qualitative_code,
        row_number() over (
            partition by traffic.product_row_id, weather.category
            order by
                weather.issued_at desc nulls last,
                weather.collected_at desc nulls last,
                weather.published_at desc nulls last
        ) as category_row_num
    from traffic
    inner join {{ ref('asac_seoul', 'gold_weather_forecast_by_admin_dong') }} as weather
        on traffic.admin_dong_code = weather.admin_dong_code
       and cast(date_trunc('hour', weather.forecast_at) as timestamp(6)) = traffic.hour_at
       and weather.issued_at <= traffic.status_observed_at
    where lower(weather.category) in ('tmp', 'pop', 'reh', 'wsd', 'sky', 'pty')
),

latest_weather_category as (
    select
        traffic_product_row_id,
        lower(category) as category,
        issued_at,
        collected_at,
        published_at,
        value_num,
        qualitative_code
    from weather_candidates
    where category_row_num = 1
),

weather_hourly as (
    select
        traffic_product_row_id,
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
    from latest_weather_category
    group by traffic_product_row_id
)

select
    traffic.product_row_id,
    traffic.admin_dong_code,
    traffic.hour_at,
    traffic.admin_dong,
    traffic.gu_code,
    traffic.gu,
    traffic.admin_dong_revision_date,
    traffic.incident_count,
    traffic.has_incident,
    traffic.quality_state,
    traffic.snapshot_as_of_at,
    traffic.status_observed_at,
    traffic.published_at,
    traffic.snapshot_dag_run_id,
    traffic.source_id,
    weather_hourly.weather_category_coverage_count,
    weather_hourly.weather_latest_issued_at,
    weather_hourly.weather_latest_collected_at,
    weather_hourly.weather_latest_published_at,
    weather_hourly.tmp_value_num,
    weather_hourly.pop_value_num,
    weather_hourly.reh_value_num,
    weather_hourly.wsd_value_num,
    weather_hourly.sky_qualitative_code,
    weather_hourly.pty_qualitative_code,
    weather_hourly.is_precipitating
from traffic
inner join canonical_admin_dong
    on traffic.admin_dong_code = canonical_admin_dong.admin_dong_code
left join weather_hourly
    on traffic.product_row_id = weather_hourly.traffic_product_row_id
