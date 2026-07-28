-- Serving Gold: latest per-link flow compared with its same KST weekday/hour history.
-- Insufficient history is retained and flagged rather than suppressed or scored.

{{ config(materialized='table') }}

with latest as (
    select
        *,
        day_of_week(observed_at_kst) as kst_day_of_week,
        hour(observed_at_kst) as kst_hour
    from {{ ref('gold_traffic_flow_link_latest') }}
),

baseline_history as (
    select
        latest.link_id,
        count(flow.link_id) as profile_observation_count,
        count(distinct cast({{ asac_axes.utc_to_kst('flow.observed_at') }} as date)) as distinct_observation_date_count,
        count_if(flow.flow_speed is not null) as speed_observation_count,
        round(approx_percentile(cast(flow.flow_speed as double), 0.25), 2) as p25_flow_speed,
        round(approx_percentile(cast(flow.flow_speed as double), 0.5), 2) as median_flow_speed,
        round(approx_percentile(cast(flow.flow_speed as double), 0.75), 2) as p75_flow_speed,
        min(cast({{ asac_axes.utc_to_kst('flow.observed_at') }} as timestamp(6))) as profile_first_observed_at_kst,
        max(cast({{ asac_axes.utc_to_kst('flow.observed_at') }} as timestamp(6))) as profile_last_observed_at_kst
    from latest
    left join {{ ref('silver_seoul_traffic_flow') }} as flow
        on latest.link_id = cast(flow.link_id as varchar)
       and latest.kst_day_of_week = day_of_week(cast({{ asac_axes.utc_to_kst('flow.observed_at') }} as timestamp(6)))
       and latest.kst_hour = hour(cast({{ asac_axes.utc_to_kst('flow.observed_at') }} as timestamp(6)))
    group by latest.link_id
),

compared as (
    select
        latest.product_row_id,
        latest.link_id,
        latest.source_id,
        latest.flow_speed,
        latest.flow_travel_time,
        latest.flow_value_quality,
        latest.observed_at_kst,
        latest.collected_at_kst,
        latest.kst_day_of_week,
        latest.kst_hour,
        baseline.profile_observation_count,
        baseline.distinct_observation_date_count,
        baseline.speed_observation_count,
        baseline.p25_flow_speed,
        baseline.median_flow_speed,
        baseline.p75_flow_speed,
        baseline.profile_first_observed_at_kst,
        baseline.profile_last_observed_at_kst,
        latest.raw_object_key,
        latest.payload_hash,
        latest.request_id,
        latest.dag_run_id,
        case
            when latest.flow_speed is null then 'current_speed_unavailable'
            when baseline.profile_observation_count = 0 then 'no_matching_profile'
            when baseline.distinct_observation_date_count < 4
              or baseline.speed_observation_count < 12 then 'insufficient_history'
            when baseline.median_flow_speed is null
              or baseline.median_flow_speed <= 0 then 'baseline_speed_unavailable'
            else 'representative'
        end as baseline_state
    from latest
    inner join baseline_history as baseline
        on latest.link_id = baseline.link_id
)

select
    product_row_id,
    link_id,
    source_id,
    flow_speed,
    flow_travel_time,
    flow_value_quality,
    observed_at_kst,
    collected_at_kst,
    kst_day_of_week,
    kst_hour,
    profile_observation_count,
    distinct_observation_date_count,
    speed_observation_count,
    p25_flow_speed,
    median_flow_speed,
    p75_flow_speed,
    profile_first_observed_at_kst,
    profile_last_observed_at_kst,
    baseline_state,
    case
        when baseline_state = 'representative'
            then round(flow_speed - median_flow_speed, 2)
    end as speed_delta_from_median,
    case
        when baseline_state = 'representative'
            then round(flow_speed / median_flow_speed, 4)
    end as speed_ratio_to_median,
    case
        when baseline_state <> 'representative' then cast(null as varchar)
        when flow_speed < p25_flow_speed then 'below_typical_range'
        when flow_speed > p75_flow_speed then 'above_typical_range'
        else 'within_typical_range'
    end as anomaly_direction,
    raw_object_key,
    payload_hash,
    request_id,
    dag_run_id
from compared
