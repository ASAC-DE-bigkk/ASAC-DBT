select *
from {{ ref('silver_seoul_traffic_incident') }}
where admin_dong_code is not null
  and (
      gu_code is null
      or gu is null
      or admin_dong is null
      or gu_code <> substr(admin_dong_code, 1, 5)
  )
