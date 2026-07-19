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

-- 정렬 스펙(#264): dataset 필터(실측 ASAC-DBT#262 M3 — dataset='general_restaurant' 단독 필터가
-- 대표 질의) + 행정동 집계(gold_license_dong_summary 등) 지역성. table 재생성 시 자동 적용.
{{ config(
    materialized='table',
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
