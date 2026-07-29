-- gold_transit_forecast_card grain (area_cd, target_hour_at) 유일성 — Serving Contract v1
-- primary_key 선언(#478 §3.1)의 고유성 근거. 중복이면 실패.
select
    area_cd,
    target_hour_at,
    count(*) as n
from {{ ref('gold_transit_forecast_card') }}
group by area_cd, target_hour_at
having count(*) > 1
