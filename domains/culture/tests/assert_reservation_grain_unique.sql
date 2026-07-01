-- 예약 gold 그레인(location_key × snapshot_date) 유일성 단언. 중복 행이 있으면 실패(>0행).
select
    location_key,
    snapshot_date,
    count(*) as n
from {{ ref('gold_culture_reservation_daily') }}
group by location_key, snapshot_date
having count(*) > 1
