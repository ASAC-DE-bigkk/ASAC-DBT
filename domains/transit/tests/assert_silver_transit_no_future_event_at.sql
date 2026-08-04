-- #66: silver 3종에 '미래 event_at'(수집시각+스큐 초과)이 0건임을 계약(error).
--   목적: transit_event_at_not_future 상한 필터가 실제로 걸렸는지 증명 —
--   매크로/var/모델 회귀로 필터가 풀리면 이 테스트가 즉시 실패한다.
--   event_at 은 KST 벽시계, ingested_at 은 UTC → asac_axes.utc_to_kst 로 환산해 비교
--   (transit_event_at_is_future 가 캡슐화). 반환 행이 있으면 미래 잔존 = 실패.
-- 스코핑(B안): 최근 var(transit_test_lookback_days)일만 스캔 — 위반 행은 정의상 event_at 이
--   수집시각보다 미래(≈현재 이후)라 항상 윈도 하한 위에 있고, 과거에 유입된 위반은 당시
--   빌드가 이미 잡았다. 필터 회귀 감지력은 그대로, 스캔만 고정 비용화.

{% set recent_window -%}
event_at >= current_date - interval '{{ var("transit_test_lookback_days") }}' day
{%- endset %}

select 'silver_transit_subway_arrival' as model, event_at, ingested_at
from {{ ref('silver_transit_subway_arrival') }}
where {{ recent_window }}
  and {{ transit_event_at_is_future('event_at', 'ingested_at') }}

union all

select 'silver_transit_parking' as model, event_at, ingested_at
from {{ ref('silver_transit_parking') }}
where {{ recent_window }}
  and {{ transit_event_at_is_future('event_at', 'ingested_at') }}

union all

select 'silver_transit_bus_position' as model, event_at, ingested_at
from {{ ref('silver_transit_bus_position') }}
where {{ recent_window }}
  and {{ transit_event_at_is_future('event_at', 'ingested_at') }}
