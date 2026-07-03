-- current grain (dataset, mgtno) 유니크 — 업소당 현재 상태는 정확히 1행.
select
    dataset,
    mgtno,
    count(*) as row_count
from {{ ref('silver_license_current') }}
group by dataset, mgtno
having count(*) > 1
