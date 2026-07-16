-- Serving Gold: dong-precise culture event days with same-day KMA planning risk.
-- Grain: (event_ref, event_date).  Forecast thresholds are non-official
-- planning signals and event rows without a precise dong are intentionally out.

{{ config(materialized='table') }}

with event_days as (
    select
        cast(event.event_ref as varchar) as event_ref,
        cast(event.event_type as varchar) as event_type,
        cast(event.title as varchar) as title,
        cast(event.venue_name as varchar) as venue_name,
        cast(event.is_free as varchar) as is_free,
        cast(event.admin_dong_code as varchar) as admin_dong_code,
        cast(event.admin_dong as varchar) as admin_dong,
        cast(event.gu_code as varchar) as gu_code,
        cast(event.gu as varchar) as gu,
        cast(day.event_date as date) as event_date
    from {{ source('weather_culture_schedule_gold', 'gold_culture_event_schedule') }} as event
    cross join unnest(sequence(event.event_start_date, event.event_end_date)) as day(event_date)
    where event.admin_dong_code is not null
      and event.quality_status = 'dong_precise'
),

weather_daily as (
    select
        wide.admin_dong_code,
        cast(wide.forecast_at as date) as forecast_date,
        min(wide.issued_at) as weather_issued_at_min,
        max(wide.issued_at) as weather_issued_at_max,
        min(wide.temp_c) as temp_min_c,
        max(wide.temp_c) as temp_max_c,
        max(wide.precip_prob_pct) as precip_prob_max_pct,
        count_if(wide.is_precipitating) as precipitation_hour_count,
        max(wide.wind_ms) as wind_max_ms,
        bool_or(alert.any_alert) as any_weather_risk,
        array_join(array_sort(array_distinct(array_agg(alert.alert_labels) filter (where alert.alert_labels is not null))), ', ') as risk_labels
    from {{ ref('gold_weather_forecast_wide_by_admin_dong') }} as wide
    left join {{ ref('gold_weather_alert_by_admin_dong') }} as alert
        on wide.product_row_id = alert.product_row_id
    group by 1, 2
)

select
    concat(event_days.event_ref, '|', cast(event_days.event_date as varchar)) as product_row_id,
    event_days.event_ref,
    event_days.event_type,
    event_days.title,
    event_days.venue_name,
    event_days.is_free,
    event_days.admin_dong_code,
    event_days.admin_dong,
    event_days.gu_code,
    event_days.gu,
    event_days.event_date,
    weather_daily.admin_dong_code is not null as weather_observation_present,
    weather_daily.weather_issued_at_min,
    weather_daily.weather_issued_at_max,
    weather_daily.temp_min_c,
    weather_daily.temp_max_c,
    weather_daily.precip_prob_max_pct,
    weather_daily.precipitation_hour_count,
    weather_daily.wind_max_ms,
    coalesce(weather_daily.any_weather_risk, false) as any_weather_risk,
    weather_daily.risk_labels
from event_days
left join weather_daily
    on event_days.admin_dong_code = weather_daily.admin_dong_code
   and event_days.event_date = weather_daily.forecast_date
