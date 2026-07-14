-- gold_license_entity_history — 업소 버전 이력(서빙 프로젝션, Iceberg 전용 · D1 export 금지).
--
-- 서빙 레이어 정책(dags docs/PROJECT.md §4): 대용량 이력은 D1(SQLite) 용량 상한 때문에 export
-- 하지 않고 Iceberg gold 에만 둔다(§4.2·§4.3). silver_license_history(append-only 변경로그)의
-- 서빙 프로젝션 — record_json/정렬키/수집 계보 제외, 버전 식별 grain 은 silver 와 동일하게
-- (dataset, opnsfteamcode, mgtno, collected_at, content_hash).
--
-- 증분(재개 표준 PROJECT.md §3): collected_at 워터마크 append — silver history 가 append-only 라
-- 워터마크 이후 신규 버전 행만 승계한다. 전량 재구축은 --full-refresh(commerce_load_gold_refresh).

{{ config(
    materialized='incremental',
    incremental_strategy='append',
    on_schema_change='fail'
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
    collected_at,
    bronze_run_id
from {{ ref('silver_license_history') }}
{% if is_incremental() %}
where collected_at > (select coalesce(max(collected_at), timestamp '1970-01-01 00:00:00') from {{ this }})
{% endif %}
