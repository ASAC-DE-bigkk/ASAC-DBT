-- 연속 중복 제거 불변식: 같은 업소의 인접 버전(version_seq)은 content_hash 가 달라야 한다.
-- (A→B→A 원복은 비인접이므로 허용. 인접 동일이 남아 있으면 dedup 결함.)
with h as (
    select
        dataset,
        mgtno,
        version_seq,
        content_hash,
        lag(content_hash) over (
            partition by dataset, mgtno order by version_seq
        ) as prev_content_hash
    from {{ ref('silver_license_history') }}
)

select dataset, mgtno, version_seq
from h
where prev_content_hash = content_hash
