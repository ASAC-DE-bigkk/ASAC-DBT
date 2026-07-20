-- silver_license_entity_history — 업소 버전 이력(원형 정리본 프로젝션).
--
-- 레이어 재분류(2026-07-15, PROJECT.md §4): 원형은 silver. 대용량 이력은 D1 export 금지
-- (§4.2·§4.3 — Iceberg 전용). silver_license_history(append-only 변경로그)의
-- 서빙 프로젝션 — record_json/정렬키/수집 계보 제외, 버전 식별 grain 은 silver 와 동일하게
-- (dataset, opnsfteamcode, mgtno, collected_at, content_hash).
--
-- 증분(재개 표준 PROJECT.md §3): collected_at 워터마크 append — silver history 가 append-only 라
-- 워터마크 이후 신규 버전 행만 승계한다. 전량 재구축은 --full-refresh(commerce_load_gold_refresh).
--
-- 청크 백필 스코프(#버그②, 2026-07-20 from-zero 드릴 실측): 워터마크는 **전역 max** 라서
-- 청크 배치가 dataset 별로 순차 실행되면 배치1이 워터마크를 올린 뒤 배치2+ 의 dataset 들이
-- (collected_at 이 그보다 과거라) 통째로 걸러진다 — 실측 152종 중 5종만 적재됨.
-- → include_datasets 가 주어지면(청크 경로) 전역 워터마크 대신 **해당 dataset 스코프의
--   자기 워터마크**로 판정한다. 같은 배치 재실행 시 중복 append 를 막기 위해 dataset 별
--   max(collected_at) 를 기준으로 한다(append 전략 유지 — 기존 계약 불변).
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
{% if var('include_datasets', []) %}
-- 청크 백필: dataset 스코프 + 그 dataset 의 자기 워터마크(전역 max 사용 금지 — 위 주석).
where cast(dataset as varchar) in ({% for v in var('include_datasets') %}'{{ v }}'{% if not loop.last %}, {% endif %}{% endfor %})
  {% if is_incremental() %}
  and collected_at > (
      select coalesce(max(collected_at), timestamp '1970-01-01 00:00:00')
      from {{ this }}
      where cast(dataset as varchar) in ({% for v in var('include_datasets') %}'{{ v }}'{% if not loop.last %}, {% endif %}{% endfor %})
  )
  {% endif %}
{% elif is_incremental() %}
where collected_at > (select coalesce(max(collected_at), timestamp '1970-01-01 00:00:00') from {{ this }})
{% endif %}
