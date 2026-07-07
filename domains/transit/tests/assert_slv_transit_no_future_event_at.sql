-- #66: silver 3종에 '미래 event_at'(수집시각+스큐 초과)이 0건임을 계약(error).
--   목적: transit_event_at_not_future 상한 필터가 실제로 걸렸는지 증명 —
--   매크로/var/모델 회귀로 필터가 풀리면 이 테스트가 즉시 실패한다.
--   event_at 은 KST 벽시계, ingested_at 은 UTC → asac_axes.utc_to_kst 로 환산해 비교
--   (transit_event_at_is_future 가 캡슐화). 반환 행이 있으면 미래 잔존 = 실패.
select 'slv_transit_subway_arrival' as model, event_at, ingested_at
from {{ ref('slv_transit_subway_arrival') }}
where {{ transit_event_at_is_future('event_at', 'ingested_at') }}

union all

select 'slv_transit_parking' as model, event_at, ingested_at
from {{ ref('slv_transit_parking') }}
where {{ transit_event_at_is_future('event_at', 'ingested_at') }}

union all

select 'slv_transit_bus_position' as model, event_at, ingested_at
from {{ ref('slv_transit_bus_position') }}
where {{ transit_event_at_is_future('event_at', 'ingested_at') }}
