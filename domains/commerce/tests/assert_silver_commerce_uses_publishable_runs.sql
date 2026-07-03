-- silver 는 발행 게이트를 통과한 (dataset, bronze_run_id) 만 반영해야 한다.
-- history 의 각 행이 SUCCESS+is_publishable manifest 에 대응하지 않으면 실패.
select history.dataset, history.bronze_run_id
from {{ ref('silver_license_history') }} as history
left join {{ source('commerce_bronze', 'collection_run_manifest') }} as manifest
    on cast(history.dataset as varchar) = cast(manifest.dataset as varchar)
    and cast(history.bronze_run_id as varchar) = cast(manifest.bronze_run_id as varchar)
    and manifest.status = 'SUCCESS'
    and manifest.is_publishable
where manifest.bronze_run_id is null
limit 1
