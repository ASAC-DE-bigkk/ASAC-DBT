-- 인허가 현재 상태(업소당 최신 1행). history 의 암묵 버저닝 정렬
-- (updatedt_sort, lastmodts_sort, observed_date, collected_at, content_hash) 내림차순 최상위.
-- grain: (dataset, opnsfteamcode, mgtno) — MGTNO 는 발급 자치단체 안에서만 유니크.
--
-- 증분(#81): materialized=incremental(delete+insert, unique_key=grain). 이번 run 에 새 history(collected_at
-- 최신)가 생긴 grain 만 그 grain 의 **전 이력 위에서** 최신 1행을 재계산해 교체한다. 비영향 grain 은 기존
-- current 유지 → 전체 재빌드 회피. **history 는 append-only(전 버전 보존)** 이라 값이 바뀌어도 이전 값은
-- history 에 그대로 남고, current 는 '최신 포인터'만 갱신한다. 정합성 전량 재계산은 --full-refresh.
{{ config(
    materialized='incremental',
    unique_key=['dataset', 'opnsfteamcode', 'mgtno'],
    incremental_strategy='delete+insert',
    on_schema_change='sync_all_columns',
) }}

with affected as (
    -- 증분: collected_at 이 기존 current 최대보다 새로운(=이번 run 신규 유입) grain. full-refresh/최초=전체.
    -- (run 은 시간순이라 이번 run 새 history 의 collected_at 은 항상 이전 current 최대보다 크다.)
    -- 청크 백필(include_datasets): 지정 dataset 의 grain 전체를 대상으로(collected_at 순서 무관) —
    -- 배치가 시간순 밖으로 들어와도 누락 없이 재계산. history 와 동일 배치로 격리.
    select distinct dataset, opnsfteamcode, mgtno
    from {{ ref('silver_license_history') }}
    {% if var('include_datasets', []) %}
    where cast(dataset as varchar) in ({% for v in var('include_datasets') %}'{{ v }}'{% if not loop.last %}, {% endif %}{% endfor %})
    {% elif is_incremental() %}
    where collected_at > (select coalesce(max(collected_at), timestamp '1970-01-01 00:00:00') from {{ this }})
    {% endif %}
),

ranked as (
    select
        h.*,
        row_number() over (
            partition by h.dataset, h.opnsfteamcode, h.mgtno
            order by h.updatedt_sort desc, h.lastmodts_sort desc,
                     h.observed_date desc, h.collected_at desc, h.content_hash desc
        ) as recency_rank
    from {{ ref('silver_license_history') }} h
    {% if is_incremental() %}
    inner join affected a
        on h.dataset = a.dataset and h.opnsfteamcode = a.opnsfteamcode and h.mgtno = a.mgtno
    {% endif %}
)

select
    dataset,
    opnsfteamcode,
    mgtno,
    record_json,          -- 원본 보존(API별 비공통 필드) → gold 가 API별 table화
    bplcnm,
    trdstategbn,
    trdstatenm,
    dtlstategbn,
    dtlstatenm,
    apvpermymd,
    dcbymd,
    sitetel,
    road_address,
    jibun_address,
    jibun_address_source,
    road_address_norm,
    jibun_address_norm,
    gu,
    gu_code,
    {{ null_if_masked_address('legal_dong') }} as legal_dong,
    {{ null_if_masked_address('legal_code') }} as legal_code,
    {{ null_if_masked_address('admin_dong') }} as admin_dong,
    {{ null_if_masked_address('admin_dong_code') }} as admin_dong_code,
    address_key_road,
    address_key_jibun,
    source_coord_x,
    source_coord_y,
    latitude,
    longitude,
    content_hash,
    updatedt,
    updatedt_ts,
    lastmodts,
    lastmodts_ts,
    observed_date,
    collected_at,
    bronze_run_id,
    dag_run_id,
    raw_object_key,
    load_date
from ranked
where recency_rank = 1
