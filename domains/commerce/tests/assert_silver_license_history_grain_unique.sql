-- history 행 유니크: (dataset, opnsfteamcode, mgtno, collected_at, content_hash).
-- 동일 content 재유입은 정렬키(UPDATEDT·LASTMODTS까지 동일)가 같아 인접 dedup 이 제거하므로,
-- 완전 동일 행이 2건 남아 있으면 dedup 결함이다. (version_seq 제거 후의 행 식별 그레인.
-- opnsfteamcode 포함 — MGTNO 는 발급 자치단체 안에서만 유니크.)
select
    dataset,
    opnsfteamcode,
    mgtno,
    collected_at,
    content_hash,
    count(*) as row_count
from {{ ref('silver_license_history') }}
group by dataset, opnsfteamcode, mgtno, collected_at, content_hash
having count(*) > 1
