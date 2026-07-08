-- gold 비율 지표 sanity: 0~1 범위 밖 값 단언 (#67).
--   bus_full_ratio / bus_stop_ratio = 0/1 플래그 평균 → [0,1].
--   parking_occupancy_avg = 현재대수/총면수 평균 → [0,1](일시 초과 만차로 1 초과 가능하나
--     정상 데이터에선 1 이하 기대. 상류 결손으로 현재는 전건 null — null 은 통과).
-- null 은 통과(집계 대상 없음/상류 결손). 범위 밖 행을 반환하면 실패.
select 'bus_full_ratio' as metric, admin_dong_code, hour_at, bus_full_ratio as value
from {{ ref('gold_transit_dong_hourly') }}
where bus_full_ratio is not null and (bus_full_ratio < 0 or bus_full_ratio > 1)
union all
select 'bus_stop_ratio', admin_dong_code, hour_at, bus_stop_ratio
from {{ ref('gold_transit_dong_hourly') }}
where bus_stop_ratio is not null and (bus_stop_ratio < 0 or bus_stop_ratio > 1)
union all
select 'parking_occupancy_avg', admin_dong_code, hour_at, parking_occupancy_avg
from {{ ref('gold_transit_dong_hourly') }}
where parking_occupancy_avg is not null and (parking_occupancy_avg < 0 or parking_occupancy_avg > 1)
