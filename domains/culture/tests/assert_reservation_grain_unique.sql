-- 스냅샷 그레인 (service_id, load_date) 유일성 단언. 중복 행이 있으면 실패(>0행).
select service_id, load_date, count(*) as n
from {{ ref('silver_culture_reservation') }}
group by service_id, load_date
having count(*) > 1
