select *
from {{ ref('gold_traffic_flow_anomaly_current') }}
where (
        baseline_state = 'representative'
        and (
            speed_delta_from_median is null
            or speed_ratio_to_median is null
            or anomaly_direction is null
        )
    )
   or (
        baseline_state <> 'representative'
        and (
            speed_delta_from_median is not null
            or speed_ratio_to_median is not null
            or anomaly_direction is not null
        )
    )
