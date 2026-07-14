-- W1 격리 스모크 전용(#159): 브릿지 모델·시드와 동일한 모드 가드.
-- dev에는 브릿지 테이블이 없으므로(환경 가드가 빌드 금지) 셀렉터 유출 시 TABLE_NOT_FOUND로
-- transform이 정지한다 — 2026-07-12 14:30Z부터 4연속 실패 사례.
{{ config(enabled=(var('weather_w1_initial_build_mode', '') == 'bounded_isolated_smoke')) }}

select bridge.source_admin_code, bridge.bridge_version, bridge.nx, bridge.ny
from {{ ref('bridge_weather_admin_dong_grid') }} bridge
left join {{ ref('asac_axes', 'dim_admin_dong') }} canonical
  on bridge.source_admin_code = canonical.admin_dong_code
where (canonical.admin_dong_code is not null and (
       bridge.admin_dong_code is distinct from canonical.admin_dong_code
    or bridge.admin_dong is distinct from canonical.admin_dong
    or bridge.gu_code is distinct from canonical.gu_code
    or bridge.gu is distinct from canonical.gu
    or bridge.admin_dong_revision_date is distinct from canonical.revision_date
    or bridge.canonical_mapping_state is distinct from 'matched'
    or bridge.canonical_join_eligible is distinct from true))
   or (canonical.admin_dong_code is null and (
       bridge.admin_dong_code is not null
    or bridge.admin_dong is not null
    or bridge.gu_code is not null
    or bridge.gu is not null
    or bridge.admin_dong_revision_date is not null
    or bridge.canonical_mapping_state is distinct from 'unmatched'
    or bridge.canonical_join_eligible is distinct from false))
