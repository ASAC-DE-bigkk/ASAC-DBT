-- 연속 중복 제거 불변식: 같은 업소의 인접 행(암묵 버전 정렬 기준)은 content_hash 가 달라야 한다.
-- (A→B→A 원복은 비인접이므로 허용. 인접 동일이 남아 있으면 dedup 결함.)
-- 업소 식별 = (dataset, opnsfteamcode, mgtno) — MGTNO 는 발급 자치단체 안에서만 유니크.
-- 정렬키는 모델의 암묵 버저닝과 동일: updatedt_sort, lastmodts_sort, observed_date, collected_at, content_hash.
with h as (
    select
        dataset,
        opnsfteamcode,
        mgtno,
        content_hash,
        lag(content_hash) over (
            partition by dataset, opnsfteamcode, mgtno
            order by updatedt_sort, lastmodts_sort, observed_date, collected_at, content_hash
        ) as prev_content_hash
    from {{ ref('silver_license_history') }}
)

select dataset, opnsfteamcode, mgtno, content_hash
from h
where prev_content_hash = content_hash
