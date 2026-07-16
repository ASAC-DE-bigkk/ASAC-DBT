# gold 카탈로그 메타데이터 — 탭별 소스 매핑 (commerce)

데이터 카탈로그의 테이블 상세 탭(개요/스키마/품질/샘플/계보/API)이 어디서 값을 읽는지 정리한다.
대부분은 **dbt 메타데이터**(schema/manifest/catalog)에서 나오므로, dbt 프로젝트를 인제스트하면 자동 채워진다.

## 탭 → 소스 매핑

| 탭 | 소스(dbt/웨어하우스) | 상태 |
|---|---|---|
| **개요** | `models/gold/_commerce_gold__models.yml` 의 model `description` (22종 전수) | ✅ |
| **스키마** | 같은 파일의 `columns[].name/data_type/description` — 22 테이블 전 컬럼(약 180개) 문서화 | ✅ |
| **품질** | 같은 파일의 `columns[].tests` — not_null·unique·accepted_values **71 테스트, 전수 PASS**(2026-07-16) | ✅ |
| **샘플** | 웨어하우스 직조회(Trino/Iceberg `iceberg_dev.commerce.<table>`) — 아래 쿼리 패턴 | ✅ |
| **계보** | dbt `ref()`/`source()` 그래프 + `models/exposures.yml`(크로스도메인 culture 포함) | ✅ |
| **API** | `models/sources.yml`(commerce_bronze) → LOCALDATA **152 API**(레지스트리) | ✅ |

> dbt docs 아티팩트로 내보내려면: `dbt docs generate` → `target/manifest.json`·`target/catalog.json`
> (DataHub/OpenMetadata 등 대다수 카탈로그가 이 둘을 인제스트해 개요/스키마/품질/계보를 채운다).

## 계보(Lineage) — 계승 체인

```
LOCALDATA 152 API (source: commerce_bronze / sources.yml)
        │  commerce_load_bronze DAG (raw NDJSON 증분)
        ▼
bronze_localdata_license  (record_json 통짜, dataset 컬럼으로 152종 구분)
        │  silver: 결측처리·표준화·중복제거·주소/좌표 파생
        ▼
silver_license_history → silver_license_current → silver_license_entity
                                                   silver_<domain>_detail ×N (카탈로그 구동)
        │  ref('silver_license_entity') + ref('commerce_dataset_taxonomy' 시드)
        │  또는 source('commerce_silver_details', 'silver_*_detail')
        ▼
gold_* 22종 (집계·지표)
        │  exposures.yml
        ├─▶ cross_domain_activity_join  ── culture.gold_culture_activity_by_dong 와
        │      행정동/gu × 기간 공통축 조인(Marquez/OpenLineage 물리명 stitch, 양방향 계약)
        └─▶ commerce_gold_serving       ── D1(SQLite) 선별 export → API·화면 6종(예정)
```

- **도메인 내 계보**: dbt 가 `ref()`/`source()` 로 자동 생성(bronze→silver→gold). Cosmos/OpenLineage 가 실행 시 이벤트를 emit → Marquez 에 물리 테이블명으로 적재.
- **크로스도메인(culture) 계승**: culture 는 `cross_domain_join_contract`(culture gold 를 타 도메인이 조인), commerce 는 대칭으로 `cross_domain_activity_join`(commerce gold 를 culture 와 조인)을 선언 → 두 도메인 dbt 그래프가 **행정동/gu × 기간 공통축**으로 이어진다. 실제 stitch 는 Marquez 가 물리 테이블명 일치로 수행.

## API(원천) — 152 LOCALDATA 인허가 API

`sources.yml` 의 `commerce_bronze.localdata_license` 가 뿌리. 152 API 는 대분류별로:

| 대분류(major) | API 수(대략) | 예시 dataset(short) |
|---|---|---|
| health(보건) | 다수 | general_restaurant · pharmacy · animal_hospital · lodging … |
| culture(문화) | 다수 | game_provider · performance · tourism · sports_facility … |
| industry(산업) | 다수 | large_store · petroleum_sale · gas · funeral … |
| environment(환경) | 13(v2) | air_pollution_facility · water_pollution_facility · waste … |

- 정본 목록: `dags/domains/commerce/config/dataset_registry.yaml`(oa_id·name_ko·short·category·sub_category·service_name).
- 특정 gold 테이블의 원천 API = 그 테이블 `dataset` 컬럼의 distinct 값. 예) `gold_detail_area_profile` = 면적 필드 보유 detail(약 40 dataset), `gold_detail_uptae_mix` = 업태 필드 보유 19 dataset.
- 한글 API 명은 registry `name_ko`(표기 규칙 `한글(영문)` — PROJECT.md §1). 서빙 라벨은 opus-serving-build-instructions.md §2.1 `d1_dim_dataset`.

## 샘플(Sample) — 조회 패턴

카탈로그 샘플 탭은 웨어하우스 직조회다. Trino 예:

```sql
-- 동네 상권 요약 top
SELECT admin_dong, gu, business_count, business_open_count, geocoded_count
FROM iceberg_dev.commerce.gold_license_dong_summary
ORDER BY business_count DESC LIMIT 5;
-- (실측 예: 역삼1동 32,452 / 신림동 31,888 / 서초1동 27,883)

-- 월별 개업 흐름
SELECT ym, event_type, major, category, gu_code, cnt
FROM iceberg_dev.commerce.gold_license_flow_monthly
WHERE major='health' AND event_type='opened'
ORDER BY ym DESC LIMIT 5;
```

> 서빙 tier·화면 매핑·지표 의도는 [serving-design.md](serving-design.md), 구현 계약은 [opus-serving-build-instructions.md](opus-serving-build-instructions.md).
