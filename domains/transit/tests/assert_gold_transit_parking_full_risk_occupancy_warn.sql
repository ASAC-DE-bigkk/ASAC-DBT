-- 주차 점유율 과대값 sanity (warn) (#406 — #231 dong_hourly 와 동일 규칙의 lot 단위판).
--   now>capacity(만차 초과)로 1 초과는 정상이나, 2 초과(200%+)는 상류 수치 이상 의심.
--   빌드를 깨지 않고(warn) 가시화만 — 정상 초과와 데이터 오류를 구분한다.
{{ config(severity='warn', tags=['hourly']) }}
select parking_id, occ_now, capacity_now, last_bucket_at
from {{ ref('gold_transit_parking_full_risk') }}
where occ_now is not null and occ_now > 2
