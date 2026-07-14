-- gold_license_entity — 업소 현재 상태(서빙 프로젝션, Iceberg 정본).
--
-- 서빙 레이어 정책(dags docs/PROJECT.md §4): gold 는 bronze/silver 와 동일한 Iceberg 카탈로그에
-- dbt 로 만들고, D1(SQLite) 에는 선별 소수 테이블만 export 한다(예정). 이 모델은 그 정본 계층의
-- "현재 상태" 테이블 — D1 export 시 필터/컬럼 축소 후보.
--
-- grain = 자연키 (dataset, opnsfteamcode, mgtno) — silver_license_current 와 1:1.
--   D1/SQLite 특성상 DB 발급 서러게이트(bigserial) 금지 → 자연키가 식별자(PROJECT.md §4.2).
-- 프로젝션: 서빙에 불필요한 대형/내부 컬럼 제외 — record_json(통짜 JSON)·주소 정규화 키·
--   버전 정렬키(_sort)·수집 계보(raw_object_key 등)는 silver 가 정본.

{{ config(materialized='table') }}

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
