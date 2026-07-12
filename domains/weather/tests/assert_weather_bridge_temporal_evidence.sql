select source_admin_code, bridge_version, nx, ny
from {{ ref('bridge_weather_admin_dong_grid') }}
where bridge_version is distinct from 'weather_admin_dong_grid_bridge_v1'
   or legacy_mapping_method is distinct from 'kma_admin_dong_grid_20260325'
   or mapping_revision_label is distinct from 'kma_admin_dong_grid_20260325'
   or recorded_at is distinct from timestamp '2026-07-04 12:38:58.000000'
   or valid_from_at is not null
   or valid_to_at is not null
   or effective_from_basis is distinct from 'repository_first_recorded_at_not_source_effective_date'
   or mapping_method is distinct from 'legacy_seed_exact_copy'
   or temporal_quality is distinct from 'revision_only'
