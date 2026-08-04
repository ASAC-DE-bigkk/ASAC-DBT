-- gold 비율 지표 sanity: 범위 밖 값 단언 (#67, #231).
--   bus_full_ratio / bus_stop_ratio = 0/1 플래그 평균 → [0,1] 불변(상·하한 모두 error).
--   parking_occupancy_avg = 현재대수/총면수 평균 → 하한 0 만 error(음수 불가). **상한 1 은
--     걸지 않는다**: now>capacity(만차 초과 주차)로 1 초과가 정상 데이터라, 상한 error 를
--     두면 정상 값에 빌드가 깨진다(#231). 과대값(>2) sanity 는 별도 warn 테스트가 본다.
-- null 은 통과(집계 대상 없음/상류 결손). 범위 밖 행을 반환하면 실패.
-- 스코핑(B안): 최근 var(transit_test_lookback_days)일만 검증 — 범위 위반은 신규 집계
--   구간(merge lookback -3h)에서 생기므로 최근 윈도로 충분. 세 분기 공통 윈도는 CTE 로 1회.
{{ config(tags=['hourly']) }}
with recent as (
    select admin_dong_code, hour_at, bus_full_ratio, bus_stop_ratio, parking_occupancy_avg
    from {{ ref('gold_transit_dong_hourly') }}
    where hour_at >= current_date - interval '{{ var("transit_test_lookback_days") }}' day
)
select 'bus_full_ratio' as metric, admin_dong_code, hour_at, bus_full_ratio as value
from recent
where bus_full_ratio is not null and (bus_full_ratio < 0 or bus_full_ratio > 1)
union all
select 'bus_stop_ratio', admin_dong_code, hour_at, bus_stop_ratio
from recent
where bus_stop_ratio is not null and (bus_stop_ratio < 0 or bus_stop_ratio > 1)
union all
select 'parking_occupancy_avg', admin_dong_code, hour_at, parking_occupancy_avg
from recent
where parking_occupancy_avg is not null and parking_occupancy_avg < 0
