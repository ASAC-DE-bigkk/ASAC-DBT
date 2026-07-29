-- gold_transit_parking_profile grain (parking_id, dow, hh) 유일성 — Serving Contract v1
-- primary_key 선언(#478 §3.1)의 고유성 근거. 중복이면 실패.
select
    parking_id,
    dow,
    hh,
    count(*) as n
from {{ ref('gold_transit_parking_profile') }}
group by parking_id, dow, hh
having count(*) > 1
