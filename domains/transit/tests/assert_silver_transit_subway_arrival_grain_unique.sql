-- silver_transit_subway_arrival grain (statn_id, ordkey, recptn_dt) 유일성. 중복이면 실패.
select
    statn_id,
    ordkey,
    recptn_dt,
    count(*) as n
from {{ ref('silver_transit_subway_arrival') }}
group by statn_id, ordkey, recptn_dt
having count(*) > 1
