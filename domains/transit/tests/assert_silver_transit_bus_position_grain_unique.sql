-- silver_transit_bus_position grain (veh_id, data_tm) 유일성. 중복이면 실패.
select
    veh_id,
    data_tm,
    count(*) as n
from {{ ref('silver_transit_bus_position') }}
group by veh_id, data_tm
having count(*) > 1
