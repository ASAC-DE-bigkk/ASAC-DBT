# silver 비공통 영역 재설계 — API(소분류) 단위 실측 + 이력 보존 + gold 정규화

> 대분류/중분류/소분류는 **조회·집계용 분류**일 뿐 테이블 설계 기준이 아니다. 이 문서는 **152종 응답
> 필드를 API 단위로 전수 실측**해 (1) 공통 밖(비공통)을 **실제로 겹치는 API끼리 하나의 카탈로그**로 묶고,
> (2) **바뀌는 값을 이력으로 보존**하고, (3) **gold가 silver 기반 정규화 + 별도 이력 테이블**을 만들며,
> (4) **각 단계(bronze→silver→gold)에 marker를 둬 값 바뀐 신규분만 증분 적재**하는 구조를 정한다.
> 인벤토리: [api-field-inventory.csv](api-field-inventory.csv) · 클러스터: [api-field-clusters.json](api-field-clusters.json).

## 0. 왜 다시 보나 — 기존 설계의 두 문제

1. **대분류 뭉치기**: `silver_license_detail_health`(#80)는 보건 8중분류를 138컬럼 sparse wide 하나에
   몰아넣는다. `dataset-columns.md §4`의 "대분류 큰 묶음"은 **dev 40종·중분류 대표 필드**라는 불완전한
   가정. API마다 필드가 다 달라 sparsity가 폭증한다.
2. **이력 미보존**: `detail_health`는 `silver_license_current`(스냅샷)에서 빌드 → **비공통 값의 과거
   버전이 남지 않는다.** "바뀌는 값은 이력으로" 요구에 어긋난다.

## 1. 실측 방법

- 152/152 데이터셋 **라이브 1페이지 프로브** → 응답 `row[0]` 키셋(전부 `INFO-000`).
- **필드 이름만** 저장 — 값·PII·URL·API키 미저장/미커밋. 원자료(값)는 레포에 두지 않는다.
- 재현: 라이브 프로브(레지스트리) 또는 적재된 `bronze_localdata_license.record_json`(Trino) 집계.

## 2. 핵심 실측 결과 (겹침 << 비겹침)

| 지표 | 값 |
|---|---|
| 데이터셋 | 152 (v1 139 + v2 13) |
| **고유 필드명(전체)** | **342개** · 평균 33.5필드/종 |
| **단 1종에만 등장** | **141개 (41%)** |
| ≤2종에만 등장 | 182개 (53%) |
| 공통 코어(≥90% 등장) | v1 **19** / v2 **21** (= 전 종 공통 14 + 준공통) |
| 비공통 필드 수/종 | 중앙값 13, 최대 31 |

→ 필드의 절반이 1~2종 고유. 작은 공통 코어 + **긴 고유 꼬리**. 겹치지 않는 데이터가 압도적(가설 확정).
공통 코어는 이미 `silver_license_current`/`history`가 `lf()`로 처리.

## 3. 겹침 클러스터 (비공통 필드셋 Jaccard, union-find)

| 임계 Jaccard | 클러스터(=테이블 수) | 단독(고유) | 최대 묶음 |
|---:|---:|---:|---:|
| 0.9 | 54 | 37 | 21 |
| **0.7 (권장)** | **37** | 19 | 21 |
| 0.5 | 26 | 13 | 34 |
| 0.3 | 17 | 10 | 52 |

> 낮은 임계는 **1~2개만 공유해도 병합**해 무관 업종을 뭉친다(@0.5의 25종 묶음은 공유 2필드). →
> **Jaccard ≈ 0.7 + 최소 공유필드 하한**으로 응집도 높은 것만 묶는다.

### @0.7 주요 클러스터 (테이블 후보)

| 후보 테이블 | 종수 | 공유 비공통필드 | 구성(예) |
|---|---:|---:|---|
| `detail_food` | 21 | **19** | general_restaurant·bakery·food_mfg·rest_restaurant·hfood_*·group_meal_* |
| `detail_amusement_arcade` | 9 | **31** | 게임장·노래방·비디오방(internet_game_cafe·karaoke_room·video_viewing_*) |
| `detail_tourism_travel` | 15 | **29** | 여행·관광·컨벤션·야영(*_travel_agency·convention_*·tour_*·campground) |
| `detail_culture_media` | 16 | 13 | 영화·음반·게임제작·출판(film_*·music_video_*·game_*·publisher) |
| `detail_sports_facility` | 11 | 11 | golf_*·fitness_center·billiard_hall·swimming_pool·martial_arts_gym |
| `detail_hygiene_beauty` | 4~5 | 15~16 | barber_shop·beauty_shop·bathhouse·laundry (+lodging 근접) |
| `detail_medical_inst` | 3 | 9 | clinic·affiliated_medical·medical_corporation |
| 계량기 4·지하수 3·담배 2·방판/통신판매 2·목재 2·직업소개 2·장례교육 2 | 2~4 | 4~7 | 소형 응집 클러스터 |
| **단독(고유 스키마)** | **19** | — | dental_lab·optical_shop·pharmacy·lodging·postpartum_care·disinfection·outdoor_advertising·traditional_temple·high_pressure_gas·medical_similar·tourism_operator |

**분류(taxonomy) ≠ 필드 구조**: '문화'는 미디어/관광/체육/게임장 **4개 별도 클러스터**로 갈리고, 식품은
21종이 한 덩어리. → 대분류 뭉치기 부적합.

## 4. 이력 보존 (필수) — 바뀌는 값은 버전으로 누적 (확인됨)

**silver는 이미 덮어쓰지 않고 이력으로 쌓는다:**
- `silver_license_history` = **append-only**. grain `(dataset, opnsfteamcode, mgtno, collected_at, content_hash)`.
  값이 바뀌면 새 `content_hash` → **새 행 추가**(과거 행 유지). **인접 중복만 제거**
  (`lag(content_hash)` 직전과 다르면 유지)라 **A→B→A 원복도 보존**. 즉 API가 바뀌었다고 그대로
  바뀌는 게 아니라 **버전 이력으로 적재**된다.
- `silver_license_current` = 그 이력의 **최신 1행 포인터**(row_number=1)일 뿐 — 이력을 대체하지 않는다.
- **비공통 값의 이력도 보존됨**: history의 각 버전 행이 `record_json`을 그대로 실어, 비공통 필드의 과거
  값도 history에 남는다. → 비공통 카탈로그를 **history에서** 추출하면 비공통도 버전 이력이 된다.
  (현행 `detail_health`는 current에서 빌드해 이 이력을 못 살림 — 재설계 대상.)

## 5. 설계 — silver(이력 원천) + gold(정규화 + 별도 이력)

레이어 역할(사용자 방향):
- **silver = 이력 원천(truth)**: `silver_license_history`(전 버전, append-only) + `silver_license_current`
  (최신 포인터) + `record_json`(비공통 원본). **공통·비공통 모두의 변경이 여기 보존된다.**
- **gold = silver 기반 정규화 + 별도 이력 테이블**:
  1. **정규화 클러스터 카탈로그** `gold_detail_<cluster>` — §3 클러스터별 1테이블, **history-form**
     (`silver_license_history`에서 추출). grain `(dataset, opnsfteamcode, mgtno, collected_at, content_hash)`
     → 비공통 값 변경도 버전으로 남음. 클러스터 API 비공통 필드 합집합을 `lf()` 컬럼화(소속 외 null).
     + 최신 포인터 뷰(선택). 임계 0.7 기준 **~12~18개**.
  2. **별도 정규화 이력 테이블** `gold_license_change_history`(사용자 계획) — silver history를 정규화한
     통합 변경 이력(업소×버전 × 상태/주소/좌표/핵심 속성, curated). 상태 전이·추이 분석의 단일 원천.
  3. **고유/희소 꼬리(41%)** — sparse 컬럼화 대신:
     - (a) `record_json` 유지(현행) — 필요 시 조회, OR
     - (b) **EAV 이력 롱테이블** `gold_license_attr(dataset, opnsfteamcode, mgtno, collected_at, field_code, field_value)`
       — 342 sparse 컬럼 없이 비공통 전량을 **버전 이력**으로 질의.

## 6. 단계별 marker & 증분 적재 (필수)

원칙: **각 단계(bronze → silver → gold)마다 "어디까지 적재했나"를 알려주는 marker/지시자**를 두고,
그 marker 이후 **값이 바뀐 신규분만** 처리한다(raw→bronze의 워터마크·diff와 동일 철학). 재개 표준
(ASAC-DAG `PROJECT.md §3`)과 정합 — 완료 제외 · 실패 이어받기 · 중단 시 미완성 drop 후 재실행.

| 단계 | marker(지시자) | 증분 단위 | 상태 |
|---|---|---|---|
| raw→bronze | `commerce_bronze_state/_watermark.json`(short별 마지막 run_id) + `bronze_collection_run_manifest`(발행) | (dataset, bronze_run_id) | **기존** ✅ — diff로 값 바뀐 신규만, 워터마크 이후만 |
| bronze→silver | `silver_load_run_marker`(dataset, bronze_run_id, `DONE`) | (dataset, bronze_run_id) | **기존** ✅ — 미마커 publishable run만 파싱·중복제거 |
| **silver→gold** | **`gold_load_run_marker`(신규 필수)** — (모델/클러스터, 반영한 silver 버전 상한) | (dataset, opnsfteamcode, mgtno, collected_at) | **신규 구현 필요** ❌ |

- **gold marker 설계**: 각 `gold_detail_<cluster>` / `gold_license_change_history` 는 자신이 반영한
  silver history의 상한(`max(collected_at)` 또는 처리한 `bronze_run_id` 집합)을 marker로 기록 →
  다음 실행은 그 이후 **신규 silver 버전만** delete+insert/append. (현행 silver current/detail의
  `where collected_at > (select max(collected_at) from {{ this }})` 증분 패턴과 동일 계약.)
- **"값 바뀐 것만" 자동 보장**: silver history가 이미 인접중복 제거(=내용 변경분만 버전 생성)라, gold는
  그 신규 버전만 받으면 자동으로 실질 변경분만 적재된다.
- **DAG 배선**: gold task는 silver `mark_silver_done` 이후 실행 → gold marker로 증분 → 완료 시 gold
  marker 기록(silver의 `mark_silver_done` 대칭). 실패 시 marker 미기록 → 재시도가 이어받음(재개 표준).

## 7. 테이블 수 결론 (이력 포함)

| 구성 | 테이블 | 이력 |
|---|---:|---|
| 공통 (기존 silver) | 2 (history/current) | ✅ append-only |
| gold 정규화 클러스터 | ~12~18 | ✅ history-form |
| gold 별도 이력 테이블 | 1 (`change_history`) | ✅ |
| (선택) EAV 이력 | 1 | ✅ |

→ 대분류(4) ❌ · per-API(152) ❌ → **공통 2 + gold 클러스터 ~12~18 + 이력 1 (+EAV 1)**.
임계값·최소 클러스터 크기는 운영 노브 — [api-field-inventory.csv](api-field-inventory.csv)로 조정.

## 8. 다음 단계 (검증 후)

1. 임계/최소크기 확정 → 클러스터·테이블 목록 픽스.
2. `gold_detail_<cluster>`(history-form) + `gold_license_change_history`(정규화 이력) 스키마 확정.
3. **`gold_load_run_marker`(신규) 설계·구현** — silver→gold 증분 지시자(§6).
4. `detail_health` → gold 클러스터로 마이그레이션(current→history 전환), `dataset-columns.md` 실측 갱신.
5. 테스트: history grain unique · 인접중복 0 · counts · **gold 증분(신규 버전만 반영)**. gold는 silver
   `ref()`만 참조(재파싱은 record_json 추출 한정).

> 재측정: 적재 완료분 기준 `bronze_localdata_license.record_json`(Trino)이 권위. 신규 데이터셋/컬럼은 동일 절차로 인벤토리 갱신.
