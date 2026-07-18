{{ config(tags=['traffic_gold_gate']) }}

with crowding_candidates as (
    select
        traffic.product_row_id,
        cast(traffic.admin_dong_code as varchar) as admin_dong_code,
        cast(traffic.hour_at as timestamp(6)) as hour_at,
        cast(crowding.area_cd as varchar) as area_cd,
        cast(crowding.event_at as timestamp(6)) as event_at,
        cast(crowding.collected_at as timestamp(6)) as collected_at,
        cast(crowding.avg_ppltn as double) as avg_ppltn
    from {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }} as traffic
    inner join {{ traffic_citydata_crowding_source_at_snapshot() }} as crowding
        on cast(traffic.admin_dong_code as varchar) = cast(crowding.admin_dong_code as varchar)
       and cast(date_trunc('hour', crowding.event_at) as timestamp(6))
            = cast(traffic.hour_at as timestamp(6))
    where crowding.area_cd is not null
),

ranked_place_hour as (
    select
        *,
        row_number() over (
            partition by admin_dong_code, hour_at, area_cd
            order by event_at desc nulls last, collected_at desc nulls last
        ) as place_hour_row_num
    from crowding_candidates
),

expected as (
    select
        product_row_id,
        count(*) as expected_monitored_place_count,
        avg(avg_ppltn) as expected_avg_place_avg_ppltn,
        max(avg_ppltn) as expected_peak_place_avg_ppltn,
        max(event_at) as expected_crowding_latest_observed_at,
        max(collected_at) as expected_crowding_latest_collected_at
    from ranked_place_hour
    where place_hour_row_num = 1
    group by product_row_id
),

gold as (
    select
        product_row_id,
        monitored_place_count,
        avg_place_avg_ppltn,
        peak_place_avg_ppltn,
        crowding_latest_observed_at,
        crowding_latest_collected_at,
        crowding_observed
    from {{ ref('gold_traffic_incident_x_citydata_crowding_current_hourly') }}
)

select
    coalesce(gold.product_row_id, expected.product_row_id) as product_row_id,
    gold.monitored_place_count,
    expected.expected_monitored_place_count,
    gold.avg_place_avg_ppltn,
    expected.expected_avg_place_avg_ppltn,
    gold.peak_place_avg_ppltn,
    expected.expected_peak_place_avg_ppltn
from gold
full outer join expected
    on gold.product_row_id = expected.product_row_id
where (
        expected.product_row_id is null
        and (
            gold.monitored_place_count is not null
            or gold.avg_place_avg_ppltn is not null
            or gold.peak_place_avg_ppltn is not null
            or gold.crowding_latest_observed_at is not null
            or gold.crowding_latest_collected_at is not null
            or gold.crowding_observed is distinct from false
        )
    )
   or (
        expected.product_row_id is not null
        and (
            gold.product_row_id is null
            or gold.monitored_place_count is distinct from expected.expected_monitored_place_count
   or gold.avg_place_avg_ppltn is distinct from expected.expected_avg_place_avg_ppltn
   or gold.peak_place_avg_ppltn is distinct from expected.expected_peak_place_avg_ppltn
   or gold.crowding_latest_observed_at
        is distinct from expected.expected_crowding_latest_observed_at
   or gold.crowding_latest_collected_at
        is distinct from expected.expected_crowding_latest_collected_at
            or gold.crowding_observed is distinct from true
        )
    )
