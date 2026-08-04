-- gold 그레인((admin_dong_code, hour_at)) 유일성 단언 (#67).
-- incremental merge 멱등의 감시: 재빌드 후에도 조합 중복 0 이어야 한다.
-- 스코핑(B안): 최근 var(transit_test_lookback_days)일만 검증 — merge 가 건드리는 구간은
--   lookback -3h 뿐이라 신규 중복은 항상 윈도 내에서 생긴다. hour_at 은 grain 축이라
--   중복 행끼리 값이 같아 윈도 경계에서 갈라지지 않는다.
{{ config(tags=['gate']) }}
select admin_dong_code, hour_at, count(*) as n
from {{ ref('gold_transit_dong_hourly') }}
where hour_at >= current_date - interval '{{ var("transit_test_lookback_days") }}' day
group by admin_dong_code, hour_at
having count(*) > 1
