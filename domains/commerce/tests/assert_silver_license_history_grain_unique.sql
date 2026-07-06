-- history grain (dataset, mgtno, version_seq) 유니크 — 조인 팬아웃/중복 버전 방지.
select
    dataset,
    mgtno,
    version_seq,
    count(*) as row_count
from {{ ref('silver_license_history') }}
group by dataset, mgtno, version_seq
having count(*) > 1
