-- slv_transit_parking grain (parking_id, event_at) 유일성. 중복 행이 있으면 실패.
select
    parking_id,
    event_at,
    count(*) as n
from {{ ref('slv_transit_parking') }}
group by parking_id, event_at
having count(*) > 1
