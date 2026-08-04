-- bronze_bus_route_master 는 주간 전체 스냅샷 적재(#471) — 전역 unique 가 아니라
-- (bus_route_id, load_date) 스냅샷 내 유일성이 계약이다. 중복이면 실패.
-- (구 source unique 테스트는 스냅샷 1개 시절 전제라 2026-07-26 2차 적재부터 오탐 → 대체)
{{ config(tags=['gate']) }}
select
    bus_route_id,
    load_date,
    count(*) as n
from {{ source('transit_bronze', 'bus_route_master') }}
group by bus_route_id, load_date
having count(*) > 1
