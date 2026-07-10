# DB/silver — 테이블 명세

silver = **명확한 공통만** 컬럼화한 이력 원천(truth). 비공통(업종별) 정규화는 gold 카탈로그가 담당
([../gold/tables.md](../gold/tables.md)). 유사도 기반 묶음은 silver 에서 하지 않는다.

## silver_license_history — 공통 이력 (원천)

| 항목 | 값 |
|---|---|
| grain | `(dataset, opnsfteamcode, mgtno, collected_at, content_hash)` — 버전 1행 |
| materialization | incremental **append-only** (pre_hook: 미마커 run 선삭제) |
| 이력 규칙 | **값 변경 = 새 버전 행 추가**(과거 유지). 인접중복만 제거 → A→B→A 원복 보존 |
| 컬럼 | 공통 canonical(v1/v2 `lf()` 병합: mgtno·opnsfteamcode·bplcnm·상태·주소·좌표·일자) + 파생(gu/동/위경도/주소키) + 버전정렬(updatedt_sort·lastmodts_sort) + 계보(bronze_run_id·raw_object_key) + **record_json(비공통 원본 보존)** |
| 소스 | `bronze_localdata_license` ⋈ `bronze_collection_run_manifest`(publishable 게이트) |

## silver_license_current — 공통 현재 포인터

| 항목 | 값 |
|---|---|
| grain | `(dataset, opnsfteamcode, mgtno)` — 업소당 최신 1행 |
| materialization | incremental delete+insert (unique_key=grain) |
| 규칙 | history 버전정렬 내림차순 row_number=1. 마스킹 주소는 동단위 null 처리 |

## 보강 참조 (Airflow 적재)

| 테이블 | grain / 적재 | 용도 |
|---|---|---|
| `bronze_ref_admin_dong` | 전량 교체 | 행정동↔법정동 매핑(서울 필터) → gu/동 코드 파생, gold_dim_region 소스 |
| `bronze_address_enrichment` | `road_address_norm` upsert | 지번 결측 Juso 보강 캐시(`status='filled'` 만 소비) |

## marker

| 테이블 | grain | 용도 |
|---|---|---|
| `silver_load_run_marker` | `(dataset, bronze_run_id, status='DONE')` | bronze→silver 증분 지시자. dbt test 통과 후 기록, 미마커=재처리 |

## (재설계 대상) silver_license_detail_health

대분류 뭉치기 + current 기반(비공통 이력 미보존) 문제로 **gold 카탈로그(detail 78)로 대체 예정** —
[../../silver-noncommon-catalogs.md](../../silver-noncommon-catalogs.md) §0.
