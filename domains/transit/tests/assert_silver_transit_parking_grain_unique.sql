-- silver_transit_parking grain (parking_id, event_at) 유일성. 중복 행이 있으면 실패.
-- 스코핑(B안): 최근 var(transit_test_lookback_days)일만 검증 — 아카이브 성장과 무관한 고정 비용.
--   event_at 은 grain 축이라 중복 행끼리 값이 같아 윈도 경계에서 갈라지지 않는다.
--   한계: merge lookback(-2h)은 ingested_at 축이라, event_at 이 오래 정지한 행(갱신 멈춘
--   lot 의 재유입 등)의 중복은 윈도 밖에 생겨 미검출될 수 있다 — 전면적 merge/dedup 회귀는
--   최근 event_at 행도 함께 중복시켜 여전히 잡히는, 클래스 단위 감시로 이해할 것.
select
    parking_id,
    event_at,
    count(*) as n
from {{ ref('silver_transit_parking') }}
where event_at >= current_date - interval '{{ var("transit_test_lookback_days") }}' day
group by parking_id, event_at
having count(*) > 1
