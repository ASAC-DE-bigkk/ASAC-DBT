-- W1 격리 스모크 전용(#159): 브릿지 모델·시드와 동일한 모드 가드.
-- dev에는 브릿지 테이블이 없으므로(환경 가드가 빌드 금지) 셀렉터 유출 시 TABLE_NOT_FOUND로
-- transform이 정지한다 — 2026-07-12 14:30Z부터 4연속 실패 사례.
{{ config(enabled=(var('weather_w1_initial_build_mode', '') == 'bounded_isolated_smoke')) }}

select source_admin_code, bridge_version, nx, ny
from {{ ref('bridge_weather_admin_dong_grid') }}
group by 1, 2, 3, 4
having count(*) > 1
    or count_if(source_admin_code is null or bridge_version is null or nx is null or ny is null) > 0
