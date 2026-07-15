-- 크로스워크 계약: silver_transit_subway_arrival 의 station_by_line 매핑
-- (seed × dim, route=line_name) 에서 (subway_id, station_name_join) 이 유일해야
-- arrival 조인이 행을 부풀리지 않는다. 다행 seed(1075·1077)를 포함해 실데이터 중복 0건 실증.
-- 중복이면 실패.
with station_by_line as (
    select
        s.subway_id,
        d.station_name_join
    from {{ ref('seoul_subway_line_code') }} s
    join {{ ref('dim_transit_station') }} d
        on d.route = s.line_name
)
select
    subway_id,
    station_name_join,
    count(*) as n
from station_by_line
group by subway_id, station_name_join
having count(*) > 1
