-- gold_transit_parking_full_risk 범위·계산 기준 단언 (#406 — 관측·baseline 분리 검증).
--   occ_now = 현재대수/총면수 → 하한 0 만 error(음수 불가). **상한 1 은 걸지 않는다**:
--     now>capacity(만차 초과 주차)로 1 초과가 정상 데이터(#231, dong_hourly ratio_range 와
--     동일 근거). 과대값(>2) sanity 는 별도 warn 테스트가 본다.
--   full_prob_now_slot = 프로파일의 만차(≥0.95) 관측 비율 → [0,1] 불변(상·하한 모두 error).
--   minutes_to_full_est = (0.95-occ)/rate, 이미 만차면 0 → 음수 불가. 또한 0 은
--     "이미 만차(occ≥0.95)" 일 때만 나온다는 계산 기준을 함께 단언한다.
--   capacity_now ≤ 0 은 error: occ_ratio 매크로가 capacity>0 관측만 비율을 정의하므로
--     occ_now 가 실린 행에 0 이하 총면수가 실리면 상류 회귀다(null 은 통과 — 상류 결손 허용).
--   rate_base_n = 최신 버킷 -45분 이내 15분 버킷 수 → grain 유일성 하에서 [1,4] 불변.
-- null 은 통과(미산출·프로파일 미보유 등 계약상 정상 결측). 범위 밖 행을 반환하면 실패.
select 'occ_now' as metric, parking_id, occ_now as value
from {{ ref('gold_transit_parking_full_risk') }}
where occ_now is not null and occ_now < 0
union all
select 'full_prob_now_slot', parking_id, full_prob_now_slot
from {{ ref('gold_transit_parking_full_risk') }}
where full_prob_now_slot is not null and (full_prob_now_slot < 0 or full_prob_now_slot > 1)
union all
select 'minutes_to_full_est', parking_id, minutes_to_full_est
from {{ ref('gold_transit_parking_full_risk') }}
where minutes_to_full_est is not null and minutes_to_full_est < 0
union all
select 'minutes_to_full_est_zero_means_full', parking_id, occ_now
from {{ ref('gold_transit_parking_full_risk') }}
where minutes_to_full_est = 0 and occ_now < 0.95
union all
select 'capacity_now', parking_id, capacity_now
from {{ ref('gold_transit_parking_full_risk') }}
where capacity_now is not null and capacity_now <= 0
union all
select 'rate_base_n', parking_id, rate_base_n
from {{ ref('gold_transit_parking_full_risk') }}
where rate_base_n is not null and (rate_base_n < 1 or rate_base_n > 4)
