# 데이터셋 컬럼 구조 — 공통 영역 / 분야별(개별) 영역과 dbt 처리 (#80)

서울 인허가(LOCALDATA) 데이터셋의 응답 컬럼은 **완전히 동일하지 않다**. **공통 영역**과
**분야별(업종군) 개별 영역**으로 나뉜다. 이 문서는 그 구조와 **dbt(silver)가 각 영역을 어떻게
'정규화 이전의 큰 정보 단위'로 묶어 다루는지**를 정리한다.

- 분류 체계(대분류/중분류/소분류) 단일 소스: ASAC-DAG `docs/PROJECT.md`.
- 공통 컬럼 근거: ASAC-DAG `docs/pipeline/common_info.md` §2, `include/commerce_core/schemas.py`
  (`COMMON_COLUMNS`/`NEAR_COMMON_COLUMNS`).

---

## 0. 크로스체크 (2026-07-09, dev bronze 실측)

`bronze_localdata_license` 를 dataset별 `record_json` 키로 실측한 결과(dev):

- **적재 40종**(v1 39 + v2 1=환경). 레지스트리 목표(수집 대상)는 **152종(v1 139 + v2 13)** — 나머지는 dev 미적재라
  분야별 필드는 적재된 40종 기준으로 확정하고, 미적재 군은 적재 시 동일 절차로 확장한다.
- 공통 **16컬럼** + 준공통 **4컬럼** (dev 40종 실측 기준 — historical). **권위 있는 최신 실측은
  ASAC-DAG `docs/pipeline/raw/api-field-coverage.md`(152종 라이브 프로브) · `docs/pipeline/common_info.md`
  참조 — v1 전 종 공통 14 + 준공통 5.** (기존 문서의 "공통 19"는 준공통 3종을 포함해 계수한 것 —
  `DCBYMD`·`SITETEL`·`SITEWHLADDR` 는 일부 군 결측이라 본 문서는 **준공통**으로 재분류.)
- 분야별 개별 필드가 방대: 식품 48 · 의료 37 · 위생·미용 34 · 안경·치과 28 · 숙박 19 ·
  축산 9 · 동물 8 · 약국 5. → 이 부분이 지금 `record_json` 에만 있어 컬럼으로 조회 불가.

---

## 1. 공통 16컬럼 — silver 기준 스키마 (전 v1 존재) *(계수는 §0 참조 — 권위 실측 v1 공통 14)*

`OPNSFTEAMCODE` `MGTNO` `BPLCNM` `APVPERMYMD` `TRDSTATEGBN` `TRDSTATENM` `DTLSTATEGBN`
`DTLSTATENM` `RDNWHLADDR` `RDNPOSTNO` `SITEPOSTNO` `LASTMODTS` `UPDATEGBN` `UPDATEDT` `X` `Y`

- 키/식별: `OPNSFTEAMCODE`+`MGTNO`(업소), 버전정렬 `UPDATEDT`→`LASTMODTS`.
- 주소/좌표: `RDNWHLADDR`(도로명), `X`/`Y`(EPSG:5174) → silver 에서 정규화·`gu`/동·`lat/lon` 파생.
- 현재 silver(`silver_license_history`/`current`)가 이 영역을 추출한다(v1/v2 는 `lf()` 매크로로 흡수).

## 2. 준공통 4컬럼 (대부분 제공, 일부 군 결측 → optional/null) *(계수는 §0 참조 — 권위 실측 준공통 5)*

`DCBYMD`(폐업일자) · `SITEWHLADDR`(지번주소) · `SITETEL`(전화) · `SITEAREA`(소재지면적)

- 지번(`SITEWHLADDR`)·전화는 대다수 제공하나 의료/약국 등 일부 군 결측. `SITEAREA` 는 식품·축산 등엔
  있으나 의료(면적은 개별 필드로 세분)·안경 등엔 없음.

## 3. 분야별(개별) 영역 — 중분류(업종군)별 큰 정보 단위

공통·준공통 밖, **업종군마다 추가되는 고유 컬럼**. dev 실측(40종) 인벤토리:

| 대분류 | 중분류(category) | 개별 필드(대표) |
|---|---|---|
| 보건 | 식품(food) | 종업원 `HOFFEPCNT`/`MANEIPCNT`/`WMEIPCNT`/`FCTYSILJOBEPCNT`, 시설 `FACILTOTSCP`/`WTRSPLYFACILSENM`/`BDNGOWNSENM`, 업태 `UPTAENM`/`SNTUPTAENM`/`TRDPJUBNSENM`, 홈페이지 `HOMEPAGE`, 관광식당/유흥은 좌석 `CAPT`/`CHAIRCNT`·무대 `STAGEAR`·객실 `STROOMCNT`·보험 `INSUR*` 추가 |
| 보건 | 의료(health_medical) | 진료과목 `MEDEXTRITEMSCN`/`MEDEXTRITEMSCNNM`, 병상 `HSTRMNUM`, 면적 `TOTAR`, 인력 `NURSECNT`/`NUTRCNT`/`ASTNEPNUM`, 산후조리(각 실면적 `*AR`, 정원 `*RGLSTNUM`), `METR*`/`SICBNUM` |
| 보건 | 위생·미용(hygiene_beauty) | 의자 `CHAIRCNT`·침대 `ABEDCNT`, 층수 `BDNG*FLRCNT`/`USE*FLR`, 세탁 `WASHMCCNT`/`RCVDRYNCNT`, 소독 `*SPRAYNUM`/`*STLZNUM`, 목욕 `YOKSILCNT`/`BALHANSILYN` |
| 보건 | 안경·치과(optical_dental) | 렌즈/검안 `LENSCUTNUM`/`PUPILDISTMEASNUM`/`SAMPLENSNUM`, 치과기공 `CRFTUSE*`/`DENTIUSEPRESSNUM`/`EFURNUM` 등 장비 수량, 면적 `TOTAR` |
| 보건 | 숙박(lodging) | 한실 `HANSHILCNT`·양실 `YANGSILCNT`, 층수 `BDNG*FLRCNT`/`USE*FLR`, 조건부허가 `CNDPERM*` |
| 보건 | 축산(livestock)·동물(animal) | 등록 `RGTMBDSNO`/`LINDSEQNO`, 업종 `LINDJOBGBNNM`/`LINDPRCBGBNNM`, 개시 `ROPNYMD`, 확인 `CFRMGBNCTN` |
| 보건 | 약국(pharmacy) | 면적 `PHARMTRDAR`, 지정일 `ASGNYMD` |
| 환경 | (v2 신형 컬럼) | 사업장/실험실 면적 `BIZOFC_AREA`/`LAB_AREA`, 구분 `BPLC_SE_NM` 등 — v2 컬럼셋(§6) |

> 문화·산업 및 미적재 환경군은 dev bronze 에 없어 개별 필드 미확정 — 적재 후 동일 실측으로 채운다.
> 전체 필드 사전(코드→의미)은 이 표를 근거로 `models/schema.yml` 및 그룹 매크로에 확장한다.

## 4. dbt 처리 — '정규화 이전 큰 정보 단위'로 분리

**공통 영역과 분야별 영역을 나누되, 완전 정규화하지 않고 대분류 단위의 큰 묶음으로 둔다.**

1. **bronze** (`bronze_localdata_license`, ASAC-DAG 적재 — dbt 는 source): dataset 컬럼으로 구분되는
   단일 changelog, `record_json` 통짜 보존 → **어떤 군의 개별 컬럼도 유실 없음**.
2. **silver 공통** (`silver_license_history`/`current`): 공통 16 + 사용 준공통을 컬럼 추출(§1). SCD 이력.
   전 API 공통이라 군별 스키마 차이에 안전. `record_json` 도 함께 보존(개별 영역 소급 추출용).
3. **silver 분야별 detail(신규, #80)**: **대분류별 detail 모델**로 개별 영역을 추출한다.
   - `silver_license_detail_health` / `_culture` / `_industry` / `_environment` (대분류=큰 정보 단위).
   - 키(`opnsfteamcode`,`mgtno`,`dataset`,버전) + 해당 대분류 datasets 의 개별 필드(`json_extract_scalar`).
   - 해당 군에 없는 필드는 자동 null(schema-on-read) — 완전 정규화(필드별 소테이블) 하지 않는다.
   - `record_json` 는 계속 보존 → 필드 추가는 모델 수정 + `--full-refresh` 백필로 소급.
   - gold 단계에서 필요한 분석 그룹만 테이블화(후속).

## 5. 개별 컬럼 추가 절차

```sql
-- 예: 위생·미용군 의자수 — 타 군에서는 자동 null
nullif(trim(json_extract_scalar(record_json, '$.CHAIRCNT')), '') as chair_cnt
```
- 추가 위치: 해당 대분류 detail 모델 `parsed` CTE + `schema.yml`. 개별 컬럼엔 not_null 금지(타 군 null 정상).
- 새 데이터셋/컬럼 재검증: ASAC-DAG `common_info.md` §5·§6, 레지스트리 `config/dataset_registry.yaml`.

## 6. v2(환경) 컬럼

환경군은 v2 신형 컬럼셋(`MNG_NO`/`OGDP_INST_CD`/`SALS_STTS_*`/`XCRD`/`YCRD` …)을 쓴다. 공통 영역은
`lf('MGTNO','MNG_NO')` 식으로 흡수하고, 개별 영역(`BIZOFC_AREA`/`LAB_AREA`/`BPLC_SE_NM` 등)은
`silver_license_detail_environment` 에서 추출한다. v1/v2 별칭: ASAC-DAG `schemas.py COLUMN_ALIASES_V2`.
