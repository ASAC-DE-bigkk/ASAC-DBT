# 39종 데이터셋 컬럼 구조 — 공통/개별 영역과 dbt 처리 방식

서울 인허가(LOCALDATA) 39종의 응답 컬럼이 **완전히 동일하지 않다**. 공통 영역과 업종군별
개별 영역으로 나뉘며, 이 문서는 그 구조와 **dbt 가 각 영역을 어떻게 다루는지**를 정리한다.

조사 근거: ASAC-DAG 번들의 실호출 검증 —
`dags/domains/commerce/docs/pipeline/common_info.md` §2(대표 5개 업종군 응답 키 교집합),
`dags/domains/commerce/include/commerce_core/schemas.py` (`COMMON_COLUMNS`/`NEAR_COMMON_COLUMNS`).

---

## 1. 결론 요약

39종 모두 LOCALDATA(지방행정 인허가데이터) 표준을 따라 **뼈대는 같지만 컬럼 수는 다르다**
(샘플 실측: 식품접객 39 · 식품판매 39 · 의료 24 · 동물 25 · 공중위생 33).

| 영역 | 컬럼 | 제공 범위 |
|---|---|---|
| **공통 (19컬럼)** | 아래 §2 표 | 39종 전부 (실호출 교집합 검증) |
| **준공통 (5컬럼)** | `SITEAREA`, `APVCANCELYMD`, `CLGSTDT`, `CLGENDDT`, `UPTAENM` | 대부분 제공하나 일부 군 누락/빈값 |
| **개별 (군 고유)** | 예: 식품접객의 좌석수·시설규모, 의료의 진료과목 등 | 업종군마다 다름 |

## 2. 공통 19컬럼 — silver 의 기준 스키마

| 컬럼 | 의미 | silver 추출 여부 |
|---|---|---|
| `OPNSFTEAMCODE` | 개방자치단체코드(발급 구청) | ✓ `opnsfteamcode` — **MGTNO 유니크 범위**(업소 식별키 구성 요소) |
| `MGTNO` | 관리번호 — 인허가 건(업소) 키, **발급 자치단체 안에서만 유니크**(실측: 교차 구청 공유 55키) | ✓ bronze 최상위 컬럼 `mgtno` |
| `BPLCNM` | 사업장명 | ✓ `bplcnm` |
| `APVPERMYMD` / `DCBYMD` | 인허가일자 / 폐업일자 | ✓ `apvpermymd` / `dcbymd` |
| `TRDSTATEGBN` / `TRDSTATENM` | 영업상태 코드/명 | ✓ `trdstategbn` / `trdstatenm` |
| `DTLSTATEGBN` / `DTLSTATENM` | 상세영업상태 코드/명 | ✓ `dtlstategbn` / `dtlstatenm` |
| `SITETEL` | 소재지 전화 | ✓ `sitetel` |
| `SITEWHLADDR` / `RDNWHLADDR` | 지번 / 도로명 주소 | ✓ `jibun_address` / `road_address` (+정규화·주소키·`gu`/동 파생). 지번 결측은 `LOTNO_ADDR`(숙박업 등 필드명 상이)→Juso 순 채움(`jibun_address_source`) — [address-and-geo.md](address-and-geo.md) |
| `SITEPOSTNO` / `RDNPOSTNO` | 우편번호 2종 | ✗ (record_json 보존) |
| `LASTMODTS` | 원천 최종수정시점 | ✓ `lastmodts`(+`lastmodts_ts`) — **버전 정렬 2순위** |
| `UPDATEGBN` | 데이터갱신 구분(I/U) | ✗ (자체 diff 로 신규/변경 판정하므로 불사용, record_json 보존) |
| `UPDATEDT` | 데이터갱신일자 | ✓ bronze 최상위 `updatedt`(+`updatedt_ts`) — **버전 정렬 1순위** |
| `X` / `Y` | 좌표(EPSG:5174 실측 판별) | ✓ `source_coord_x` / `source_coord_y` 보존 + **`latitude`/`longitude`**(WGS84 순수 계산 변환, bbox 밖 null) — [address-and-geo.md](address-and-geo.md) |

## 3. 준공통 5컬럼 (일부 군 누락 → optional)

| 컬럼 | 의미 | 누락되는 군(샘플 기준) |
|---|---|---|
| `SITEAREA` | 소재지 면적 | 공중위생 |
| `APVCANCELYMD` | 인허가취소일자 | 식품(접객·판매) |
| `CLGSTDT` / `CLGENDDT` | 휴업 시작/종료일 | 식품(접객·판매) |
| `UPTAENM` | 업태명 | 동물·공중위생(빈 값) |

현재 silver 는 이 5종을 추출하지 않는다. 필요해지면 §5 방식으로 추가하되,
**누락 군에서는 null** 이 됨을 전제로 모델·테스트를 설계할 것.

## 4. dbt 는 이 구조를 어떻게 처리하는가

**전략: 단일 테이블 + schema-on-read.** 39종을 테이블 39벌로 나누지 않는다.

1. **bronze** (`bronze_localdata_license`, ASAC-DAG 가 적재 — dbt 는 source 로만 참조):
   39종이 `dataset` 컬럼으로 구분되는 **단일 테이블**. 개별 영역을 포함한 원본 레코드
   전체가 `record_json`(varchar) 통짜로 보존되므로 **어떤 군의 고유 컬럼도 유실되지 않는다**.
   source 정의: [models/sources.yml](../models/sources.yml).
2. **silver** ([models/silver/silver_license_history.sql](../models/silver/silver_license_history.sql)):
   `json_extract_scalar(record_json, '$.<FIELD>')` 로 **공통 19컬럼 중 사용 필드만** 추출
   (`parsed` CTE). 39종 전부에 존재가 검증된 필드만 추출하므로 군별 스키마 차이에 안전하다.
   결측·타임존 규약: [timestamps-and-nulls.md](timestamps-and-nulls.md).
3. **current** ([models/silver/silver_license_current.sql](../models/silver/silver_license_current.sql)):
   history 정렬 최신 1행 — 재파싱 없음.

## 5. 개별(군 고유) 컬럼이 필요해지면

원본이 `record_json` 에 있으므로 모델 수정 후 full-refresh 백필로 소급 적용된다.

```sql
-- 예: 식품접객군의 좌석수 — 타 군에서는 자동으로 null
nullif(trim(json_extract_scalar(record_json, '$.SITEAREA')), '') as site_area
```

- 추가 위치: `silver_license_history.sql` 의 `parsed` CTE + 최종 select + `schema.yml`.
- 특정 군 전용 분석이 필요하면 `where dataset in (...)` 파생 모델을 만들고,
  공통 19컬럼 밖의 필드에는 not_null 테스트를 걸지 말 것(타 군 null 정상).
- 새 데이터셋 추가/컬럼 재검증 절차는 ASAC-DAG 쪽 `common_info.md` §5·§6 (레지스트리:
  `dags/domains/commerce/config/dataset_registry.yaml`) 을 따른다.
