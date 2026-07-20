-- silver_license_entity — 업소 현재 상태(원형 정리본 — JOIN 가능한 모델링).
--
-- 레이어 재분류(2026-07-15 사용자 확정, dags docs/PROJECT.md §4): 테이블 원형(정리·표준화·
-- JOIN 모델링)은 **silver**, 업무 목적 집계·지표만 gold. 이 모델은 silver_license_current 의
-- 서빙 프로젝션(원형) — record_json 등 내부 컬럼을 제외한 "정리된 테이블 단위". gold 집계
-- (gold_license_dong_summary)와 D1 export 가 이걸 입력으로 쓴다.
--
-- grain = 자연키 (dataset, opnsfteamcode, mgtno) — silver_license_current 와 1:1.
--   D1/SQLite 특성상 DB 발급 서러게이트(bigserial) 금지 → 자연키가 식별자(PROJECT.md §4.2).
-- 프로젝션: 서빙에 불필요한 대형/내부 컬럼 제외 — record_json(통짜 JSON)·주소 정규화 키·
--   버전 정렬키(_sort)·수집 계보(raw_object_key 등)는 silver 가 정본.
--
-- 증분 전환(#267): 기존 materialized=table 은 매 run <model>__dbt_tmp-<uuid> 물리 디렉터리를
-- 새로 만들고 직전 세대를 sibling 고아로 남겼다(매일 ~523MB 누적 — #74/ASAC-DBT#262 후속 실측).
-- silver_license_current 와 동일한 delete+insert 증분으로 전환해 churn 을 **테이블 location 내부**로
-- 옮긴다(네이티브 expire_snapshots/remove_orphan_files 가 안전 관리 — sibling 고아 미발생).
-- current 가 이미 grain 당 최신 1행이므로, entity 는 current 를 그대로 프로젝션하되 이번 run 에
-- collected_at 이 진전된 grain(=current 가 갱신한 grain)만 재적재한다. 최초/--full-refresh=전량.
-- 청크 백필(include_datasets)은 collected_at 순서와 무관하게 해당 dataset grain 전체를 재적재(current 계약과 동일).
{{ config(
    materialized='incremental',
    unique_key=['dataset', 'opnsfteamcode', 'mgtno'],
    incremental_strategy='delete+insert',
    on_schema_change='sync_all_columns',
    properties={
        "sorted_by": "ARRAY['dataset','admin_dong_code']",
    },
) }}

select
    dataset,
    opnsfteamcode,
    mgtno,
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
    gu,
    gu_code,
    legal_dong,
    legal_code,
    admin_dong,
    admin_dong_code,
    latitude,
    longitude,
    updatedt,
    updatedt_ts,
    lastmodts_ts,
    content_hash,
    observed_date,
    collected_at
from {{ ref('silver_license_current') }}
{% if var('include_datasets', []) %}
where cast(dataset as varchar) in ({% for v in var('include_datasets') %}'{{ v }}'{% if not loop.last %}, {% endif %}{% endfor %})
    {{ key_bucket_filter("coalesce(cast(opnsfteamcode as varchar), '') || '|' || coalesce(cast(mgtno as varchar), '')") }}
{% elif is_incremental() %}
-- 증분 워터마크: current 가 이번 run 에 갱신한 grain 만(collected_at 진전). current 자체가 grain 당 1행이라 안전.
where collected_at > (select coalesce(max(collected_at), timestamp '1970-01-01 00:00:00') from {{ this }})
{% endif %}
