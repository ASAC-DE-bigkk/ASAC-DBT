-- W1 격리 스모크 전용(#159): 브릿지 모델·시드와 동일한 모드 가드.
-- dev에는 브릿지 테이블이 없으므로(환경 가드가 빌드 금지) 셀렉터 유출 시 TABLE_NOT_FOUND로
-- transform이 정지한다 — 2026-07-12 14:30Z부터 4연속 실패 사례.
{{ config(enabled=(var('weather_w1_initial_build_mode', '') == 'bounded_isolated_smoke')) }}

-- 허용 증거 프로필 2종: legacy exact copy(427행) 또는 용신동 수동 centroid backfill(1행, 2026-07-23).
select source_admin_code, bridge_version, nx, ny
from {{ ref('bridge_weather_admin_dong_grid') }}
where bridge_version is distinct from 'weather_admin_dong_grid_bridge_v1'
   or valid_from_at is not null
   or valid_to_at is not null
   or effective_from_basis is distinct from 'repository_first_recorded_at_not_source_effective_date'
   or temporal_quality is distinct from 'revision_only'
   or not (
        (
            legacy_mapping_method = 'kma_admin_dong_grid_20260325'
            and mapping_revision_label = 'kma_admin_dong_grid_20260325'
            and recorded_at = timestamp '2026-07-04 12:38:58.000000'
            and mapping_method = 'legacy_seed_exact_copy'
        )
        or (
            source_admin_code = '1123053600'
            and legacy_mapping_method is null
            and mapping_revision_label = 'manual_yongsin_backfill_20260723'
            and recorded_at = timestamp '2026-07-23 12:00:00.000000'
            and mapping_method = 'manual_centroid_backfill'
        )
   )
