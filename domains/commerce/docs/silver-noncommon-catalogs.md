# 비공통 영역 재설계 — API 단위 실측 + 이력 + 카탈로그 기반 gold

> 대분류/중분류/소분류는 **조회·집계용 분류**일 뿐 테이블 설계 기준이 아니다. 152종 응답 필드를 **API
> 단위로 전수 실측**해 정한다: (1) silver는 **명확한 공통만**, (2) 비공통은 **명확히 겹치는 것만 공통
> 테이블·나머지는 단독 테이블**, (3) 전부 **이력(collected_at) 보존**, (4) **gold 카탈로그를 먼저 만들고
> 그 카탈로그로 gold 테이블 생성**, (5) **각 단계 marker로 증분 + 중단 방어**.
> 인벤토리 [api-field-inventory.csv](api-field-inventory.csv) · 클러스터 [api-field-clusters.json](api-field-clusters.json) · **gold 카탈로그 [gold-catalog.csv](gold-catalog.csv)**.

## 0. 기존 설계의 두 문제

1. **대분류 뭉치기**: `silver_license_detail_health`(#80)가 보건 8중분류를 138컬럼 sparse wide 하나에
   몰아넣음(dev 40종·중분류 대표 필드라는 불완전한 가정). API마다 필드가 달라 sparsity 폭증.
2. **이력 미보존**: `detail_health`가 `silver_license_current`(스냅샷)에서 빌드 → 비공통 값의 과거 버전 소실.

## 1. 실측 방법

- 152/152 라이브 1페이지 프로브 → 응답 `row[0]` 키셋(전부 `INFO-000`).
- **필드 이름만** 저장(값·PII·URL·API키 미저장). 재현: 라이브 프로브 또는 `bronze_localdata_license.record_json`(Trino).

## 2. 핵심 실측 결과 (겹침 << 비공통)

| 지표 | 값 |
|---|---|
| 데이터셋 | 152 (v1 139 + v2 13) |
| 고유 필드명 | **342개** · 평균 33.5/종 |
| **단 1종에만 등장** | **141개 (41%)** · ≤2종 182 (53%) |
| 공통 코어(≥90%) | v1 **19** / v2 **21** (전 종 공통 14 + 준공통) |

→ 필드 절반이 1~2종 고유. 작은 공통 코어 + 긴 고유 꼬리 = 겹치지 않는 데이터가 압도적.

## 3. 겹침 클러스터 (비공통 Jaccard, union-find)

**분류(taxonomy) ≠ 필드구조**: '문화'는 미디어/관광/체육/게임장 4개로 갈리고, 식품은 21종이 19필드
공유 한 덩어리. → 유사도로 함부로 묶지 않고 **명확히 겹치는 것만** 공통 테이블로. 나머지 단독.

| 기준 | 클러스터 | 단독 |
|---|---:|---:|
| Jaccard 0.9 | 54 | 37 |
| Jaccard 0.7 | 37 | 19 |
| **채택(엄격): 0.7 ∧ 멤버≥3 ∧ 공유≥8** | **8** | **70** |
| Jaccard 0.5 | 26 | 13 |

→ **엄격 경계 채택**(사용자 확정): 명확히 겹치는 8개만 공통 detail, 나머지 70개는 전부 단독 detail.

## 4. 이력 보존 (필수) — 바뀌는 값은 버전으로 누적 (확인됨)

- `silver_license_history` = **append-only + 인접중복만 제거**(직전과 content_hash 다르면 새 행) →
  값 변경 시 **새 버전 행 추가**(A→B→A 보존). API가 바뀌었다고 덮어쓰지 않는다.
- `silver_license_current` = 최신 1행 포인터. **비공통 이력은 history의 `record_json`에 보존** →
  비공통 카탈로그를 history에서 추출하면 비공통도 버전 이력. (현행 detail_health는 current 기반 → 소실.)

## 5. 설계 — silver(명확한 공통·이력) + gold(카탈로그→테이블·이력)

### 5.1 silver = 명확한 공통만 (유사도 클러스터링 금지)
- `silver_license_history`(전 버전, append-only) + `silver_license_current`(포인터) + `record_json`.
- **공통 코어(14~19)와 파생만 컬럼화.** 비공통은 유사도로 묶지 않는다(그건 gold). record_json으로 원본 보존.

### 5.2 gold = 카탈로그 먼저 → 카탈로그로 테이블 생성 (§4번 요구)
**Step A. gold 카탈로그** [gold-catalog.csv](gold-catalog.csv) — **테이블화 예정 형태의 스펙**:
`table, kind(cluster|single), members(API들), key_columns, payload_columns(비공통 필드)`.
실측(field-inventory)에서 규칙으로 산출 — 명확한 공통(cluster) vs 단독(single):
- **cluster(공통 테이블)**: Jaccard≥0.7 군집이면서 `members≥2 AND 공유 비공통필드≥5`(=명확히 겹침).
- **single(단독 테이블)**: 그 외(고유 스키마·느슨한 군집) 전부.

현재 카탈로그 산출: **cluster 13 + single 58 = 71개 detail 테이블**(152종 커버). 표 이름은 sub_category
기반 자동 — 정제 가능.

| 대표 cluster | 종수 | 공유 | 구성(예) |
|---|---:|---:|---|
| `gold_detail_sale`(식품) | 21 | 19 | general_restaurant·bakery·food_mfg·hfood_* |
| `gold_detail_game`(게임장·노래방) | 9 | 31 | internet_game_cafe·karaoke_room·video_viewing_* |
| `gold_detail_tourism` | 15 | 29 | *_travel_agency·convention_*·tour_*·campground |
| `gold_detail_film_video` | 16 | 13 | film_*·music_video_*·game_제작·publisher |
| `gold_detail_sports` | 11 | 11 | golf_*·fitness_center·billiard_hall·swimming_pool |
| `gold_detail_beauty`(위생미용) | 4 | 16 | barber_shop·beauty_shop·bathhouse·laundry |
| `gold_detail_amusement` · `_institution`(의료) · `_pollution` · `_manure` · `_timber` … | 2~3 | 5~24 | 소형 명확 그룹 |
| **single 58개** | 1 | — | dental_lab·optical_shop·pharmacy·lodging·postpartum_care·groundwater_*·animal_* … |

**Step B. 카탈로그로 gold 테이블 생성 — Supertype/Subtype** (사용자 확정 구조, 상세:
[DB/gold/tables.md](DB/gold/tables.md)):
- **`gold_business_entity`(공통 supertype)**: 모든 API 업소가 먼저 여기 적재(현재 1행).
  `entity_id` = sha256(dataset|opnsfteamcode|mgtno) 결정적 서러게이트. entity_type/detail_table 로
  어느 detail 로 갈지 분기.
- **`gold_business_entity_history`(별도 이력 테이블)**: 공통 속성의 버전 이력
  `(entity_id, collected_at, content_hash)` — silver history 정규화.
- **detail 78개(cluster 8 + single 70)**: 공통 컬럼 재저장 없이 **entity_id + 버전키만 배치해 매핑**
  (§2번 요구). payload = 비공통 필드(`lf()` 추출, 소스코드 lowercase). **전부 history-form** —
  비공통 값 변경도 collected_at 버전으로 남음.
- **dim(code 정규화)**: `gold_dim_region`(행정동/법정동 — 대표 사례) · `gold_dim_business_status`(v1/v2
  분리) · `gold_dim_dataset`(152) — entity/detail 은 코드만, 이름은 dim. 반복 code값은 동일 원칙으로 추가 분리.
- **view = 조회 인터페이스**: 도메인 8×2 + API 152×2(current/history) — 물리 테이블 비노출, 카탈로그
  기반 jinja 생성. 상세: [DB/gold/views.md](DB/gold/views.md).

### 5.3 cluster 명명 (도메인 의미 기반 — sub_category/컬럼명 금지)
`food_sanitation_business`(식품위생업 21) · `media_content_business`(미디어콘텐츠 16) ·
`tourism_business`(관광사업 15) · `sports_facility`(체육시설 11) · `game_entertainment_venue`
(게임·노래·비디오 이용업소 9) · `public_sanitation_service`(공중위생 4) · `medical_institution`(3) ·
`amusement_park`(3). 후보/추천 근거: [DB/gold/tables.md §4](DB/gold/tables.md).

## 6. 단계별 marker & 증분 + 중단 방어 (필수)

각 단계에 "어디까지 적재했나" marker → 그 이후 **값 바뀐 신규분만** 처리(raw→bronze 철학 동일).

| 단계 | marker | 상태 |
|---|---|---|
| raw→bronze | `_watermark.json` + `bronze_collection_run_manifest` | 기존 ✅ |
| bronze→silver | `silver_load_run_marker`(dataset, bronze_run_id, DONE) | 기존 ✅ |
| **silver→gold** | **`gold_load_run_marker`(신규)** — **`collected_at` 워터마크** | **구현 필요** ❌ |

- **gold marker = collected_at**(§3번 요구): 각 gold 테이블이 반영한 silver `max(collected_at)` 기록 →
  다음 실행은 그 이후 신규 버전만 delete+insert/append.
- **중단 방어(§3번 요구) — 확실히**: 적재 중 끊기면 부분 반영이 남지 않게 —
  1. **DONE 지시자**: gold도 처리 완료 run/collected_at 상한을 **완료 후에만** marker 기록(silver `mark_silver_done` 대칭).
  2. **미완성 drop**: 실패 시 marker 미기록 → 다음 실행이 **미마커(미완성) 구간을 선삭제 후 재적재**
     (silver `delete_unmarked_...` 대칭) 또는 그 gold 파티션/버전 전체 drop 후 재실행.
  → PROJECT.md §3 재개 표준과 정합(완료 제외·실패 이어받기·중단 시 미완성 drop).

## 7. 테이블/뷰 수 결론 (확정 카탈로그)

| 구성 | 수 | 이력 |
|---|---:|---|
| silver 공통(기존) | 2 (history/current) | ✅ append-only |
| gold core | 2 (`business_entity` + `business_entity_history`) | ✅ 별도 이력 |
| gold dim(code 정규화) | 3 (dataset/region/status) | 스냅샷 |
| gold detail — **명확 cluster** | **8** | ✅ history-form |
| gold detail — **단독(single)** | **70** | ✅ history-form |
| gold marker | 1 (`gold_load_run_marker`, collected_at+중단방어) | — |
| **gold view(조회 인터페이스)** | 도메인 8×2 + API 152×2 | current+history |

전체 명세: **[DB/README.md](DB/README.md)**(ERD) · [DB/silver/tables.md](DB/silver/tables.md) ·
[DB/gold/tables.md](DB/gold/tables.md) · [DB/gold/views.md](DB/gold/views.md) ·
기계용 [gold-catalog.csv](gold-catalog.csv).

## 8. 다음 단계 (검증 후)

1. ~~카탈로그 경계·이름~~ → **확정됨**(엄격 8+70, 도메인 명명). 남은 검증: cluster 이름 최종 승인.
2. gold-catalog 를 **dbt seed 화** → jinja 루프로 entity/detail/view 생성(카탈로그=단일 소스).
3. **`gold_load_run_marker`(collected_at) + 중단 방어**(DONE 후행 기록·미완성 drop) 구현.
4. `detail_health` → gold 카탈로그로 마이그레이션, `dataset-columns.md` 실측 갱신.
5. 테스트: grain unique · 인접중복 0 · entity↔detail 정합(버전 1:1) · gold 증분(신규 버전만) ·
   재적재/중단 재개 · view 컴파일.
