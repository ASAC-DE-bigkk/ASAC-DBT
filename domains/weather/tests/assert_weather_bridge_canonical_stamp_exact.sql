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
