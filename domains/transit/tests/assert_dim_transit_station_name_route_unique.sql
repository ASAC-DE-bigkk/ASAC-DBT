-- dim_transit_station 조인 계약: (station_name_join, route) 은 유일해야 한다.
-- arrival 은 이 조합을 통해 dim 에 매핑되므로 중복 시 조인이 행을 부풀린다. 중복이면 실패.
select
    station_name_join,
    route,
    count(*) as n
from {{ ref('dim_transit_station') }}
group by station_name_join, route
having count(*) > 1
