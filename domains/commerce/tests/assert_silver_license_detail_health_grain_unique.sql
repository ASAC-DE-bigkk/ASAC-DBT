-- 보건 detail grain (dataset, opnsfteamcode, mgtno) 유니크 — 업소당 개별영역 1행.
-- silver_license_current(그레인 유니크) + taxonomy(short 1:1) 조인이므로 유니크가 유지되어야 한다.
select
    dataset,
    opnsfteamcode,
    mgtno,
    count(*) as row_count
from {{ ref('silver_license_detail_health') }}
group by dataset, opnsfteamcode, mgtno
having count(*) > 1
