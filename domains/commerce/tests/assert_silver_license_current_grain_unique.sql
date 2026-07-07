-- current grain (dataset, opnsfteamcode, mgtno) 유니크 — 업소당 현재 상태는 정확히 1행.
-- (MGTNO 는 발급 자치단체 안에서만 유니크 — 교차 구청 공유 키 실측 55건.)
select
    dataset,
    opnsfteamcode,
    mgtno,
    count(*) as row_count
from {{ ref('silver_license_current') }}
group by dataset, opnsfteamcode, mgtno
having count(*) > 1
