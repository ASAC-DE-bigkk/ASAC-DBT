-- 주차 점유율 과대값 sanity (warn) (#231).
--   now>capacity(만차 초과)로 1 초과는 정상이나, 2 초과(200%+)는 상류 수치 이상 의심.
--   빌드를 깨지 않고(warn) 가시화만 — 정상 초과와 데이터 오류를 구분한다.
{{ config(severity='warn') }}
select admin_dong_code, hour_at, parking_occupancy_avg
from {{ ref('gold_transit_dong_hourly') }}
where parking_occupancy_avg is not null and parking_occupancy_avg > 2
