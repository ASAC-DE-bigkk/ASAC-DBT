-- 7/7 회귀(설계 §5 라이브 게이트): 7/7 자정 전멸 run 이 사후 판정되는지.
-- 기대: scheduled_slo_passed=false ∧ eod_slo_passed=true ∧ green_disguise_runs>=1.
-- bronze 에 7/7 리포트가 실려야 판정 가능 → 게이트 후 로더 첫 실행(전량 백필) 뒤 활성.
-- 그 전엔 7/7 행이 없어 0행(통과). AC 는 라이브에서 확인.
{{ config(tags=['slo']) }}
select event_date
from {{ ref('gold_culture_slo_daily') }}
where event_date = date '2026-07-07'
  and not (
        scheduled_slo_passed = false
    and eod_slo_passed = true
    and green_disguise_runs >= 1
  )
