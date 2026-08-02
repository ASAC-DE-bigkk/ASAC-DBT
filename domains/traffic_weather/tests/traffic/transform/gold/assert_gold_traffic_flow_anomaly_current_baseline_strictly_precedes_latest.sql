{{ config(tags=['traffic_gold_gate']) }}

select *
from {{ ref('gold_traffic_flow_anomaly_current') }}
where profile_last_observed_at_kst is not null
  and profile_last_observed_at_kst >= observed_at_kst
