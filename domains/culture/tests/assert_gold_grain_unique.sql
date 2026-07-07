-- gold 그레인(gu_code × event_date) 유일성 단언.
select gu_code, event_date, count(*) as n
from {{ ref('gold_culture_location_daily') }}
group by gu_code, event_date
having count(*) > 1
