-- Traffic canonical current-hourly rows enriched with Seoul Citydata place crowding context.
-- Grain: one row per Traffic product_row_id / admin_dong_code / hour_at.
-- Crowding metrics describe monitored places only, not home-population or district totals.

{{ config(materialized='table') }}

with traffic as (
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

crowding_candidates as (
    select
        traffic.product_row_id as traffic_product_row_id,
        traffic.admin_dong_code,
        traffic.hour_at,
        cast(crowding.area_cd as varchar) as area_cd,
        cast(crowding.event_at as timestamp(6)) as event_at,
        cast(crowding.collected_at as timestamp(6)) as collected_at,
        cast(crowding.avg_ppltn as double) as avg_ppltn
    from traffic
    inner join {{ source('citydata_gold', 'gold_citydata_ppltn_by_time') }} as crowding
        on traffic.admin_dong_code = crowding.admin_dong_code
       and cast(date_trunc('hour', crowding.event_at) as timestamp(6)) = traffic.hour_at
),

ranked_place_hour as (
    select
        *,
        row_number() over (
            partition by admin_dong_code, hour_at, area_cd
            order by event_at desc nulls last, collected_at desc nulls last
        ) as place_hour_row_num
    from crowding_candidates
    where area_cd is not null
),

latest_place_hour as (
    select
        traffic_product_row_id,
        area_cd,
        event_at,
        collected_at,
        avg_ppltn
    from ranked_place_hour
    where place_hour_row_num = 1
),

crowding_hourly as (
    select
        traffic_product_row_id,
        count(*) as monitored_place_count,
        avg(avg_ppltn) as avg_place_avg_ppltn,
        max(avg_ppltn) as peak_place_avg_ppltn,
        max(event_at) as crowding_latest_observed_at,
        max(collected_at) as crowding_latest_collected_at,
        true as crowding_observed
    from latest_place_hour
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
    crowding_hourly.monitored_place_count,
    crowding_hourly.avg_place_avg_ppltn,
    crowding_hourly.peak_place_avg_ppltn,
    crowding_hourly.crowding_latest_observed_at,
    crowding_hourly.crowding_latest_collected_at,
    coalesce(crowding_hourly.crowding_observed, false) as crowding_observed
from traffic
left join crowding_hourly
    on traffic.product_row_id = crowding_hourly.traffic_product_row_id
