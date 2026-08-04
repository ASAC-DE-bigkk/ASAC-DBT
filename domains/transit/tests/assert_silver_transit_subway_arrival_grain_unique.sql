-- silver_transit_subway_arrival grain (statn_id, ordkey, recptn_dt) 유일성. 중복이면 실패.
-- 스코핑(B안): 최근 var(transit_test_lookback_days)일만 검증 — 아카이브 성장과 무관한 고정 비용.
--   윈도 축은 event_at: recptn_dt(varchar)의 결정론적 파생이라 같은 grain 의 중복 행은
--   event_at 도 같아 윈도 경계에서 갈라지지 않는다.
--   한계: merge lookback(-2h)은 ingested_at 축이라 event_at 이 오래된 행의 재유입 중복은
--   윈도 밖일 수 있다 — 전면적 merge 회귀는 최근 행에서 여전히 잡히는 클래스 단위 감시.
{{ config(tags=['gate']) }}
select
    statn_id,
    ordkey,
    recptn_dt,
    count(*) as n
from {{ ref('silver_transit_subway_arrival') }}
where event_at >= current_date - interval '{{ var("transit_test_lookback_days") }}' day
group by statn_id, ordkey, recptn_dt
having count(*) > 1
