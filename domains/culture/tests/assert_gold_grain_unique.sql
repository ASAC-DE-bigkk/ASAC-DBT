-- gold 그레인(location_key × event_date)이 유일한지 단언. 중복 행이 있으면 실패(>0행).
select
    location_key,
    event_date,
    count(*) as n
from {{ ref('gold_culture_location_daily') }}
group by location_key, event_date
having count(*) > 1
