-- gold 그레인((admin_dong_code, hour_at)) 유일성 단언 (#67).
-- incremental merge 멱등의 감시: 재빌드 후에도 조합 중복 0 이어야 한다.
select admin_dong_code, hour_at, count(*) as n
from {{ ref('gold_transit_dong_hourly') }}
group by admin_dong_code, hour_at
having count(*) > 1
