# DB/gold — 테이블 명세 (Supertype/Subtype + code 정규화 + 이력)

gold = silver(이력 원천)를 **정규화**한 서빙 레이어. 구조는 **Supertype(공통 entity) / Subtype(상세
detail)**: 모든 API 데이터는 먼저 `gold_business_entity`에 들어가고, 비공통 영역은 detail 테이블이
`entity_id`로 매핑한다(공통 컬럼 재저장 없음). code성 값(행정동/상태/데이터셋)은 dim으로 분리.
전체 카탈로그(payload 컬럼 포함): [../../gold-catalog.csv](../../gold-catalog.csv) · 조회는 view
([views.md](views.md)) 우선.

## 1. Core — Supertype + 이력 + marker

### gold_business_entity (공통 supertype — 현재)

| 항목 | 값 |
|---|---|
| grain | `(entity_id)` — 업소 1행(현재 상태) |
| PK | `entity_id` = sha256(`dataset\|opnsfteamcode\|mgtno`) **결정적 서러게이트**(재빌드 불변) |
| 소스 | `silver_license_current` |

| 컬럼 | 설명 |
|---|---|
| entity_id | PK(위 규칙) |
| dataset, opnsfteamcode, mgtno | 자연키(원 API 식별) — dataset → `gold_dim_dataset` |
| **entity_type, detail_table** | 어느 detail 로 연결되나(분기 지시자 — 카탈로그에서 부여) |
| business_name | 상호(bplcnm) |
| status_code, detail_status_code | 영업상태 코드 → `gold_dim_business_status`(이름은 dim) |
| opened_at, closed_at | 인허가일/폐업일 |
| road_address, jibun_address | 주소 |
| gu_code, legal_code, admin_dong_code | 지역 코드 → `gold_dim_region`(이름은 dim — code 정규화) |
| longitude, latitude | WGS84 좌표 |
| first_collected_at, last_collected_at, content_hash | 수집 계보/현재 버전 |

### gold_business_entity_history (공통 변경 이력 — 별도 이력 테이블)

| 항목 | 값 |
|---|---|
| grain | `(entity_id, collected_at, content_hash)` — **값 변경 = 버전 1행** |
| 소스 | `silver_license_history`(append-only) 정규화 |
| 컬럼 | entity_id + 버전키 + 공통 속성(상호/상태코드/주소/지역코드/좌표/일자/observed_date) |

### gold_load_run_marker (증분 지시자)

| 항목 | 값 |
|---|---|
| grain | `(model_name)` |
| 컬럼 | model_name, **watermark_collected_at**, status('DONE'), rows_loaded, marked_at |
| 규칙 | ① 각 gold 모델은 반영한 silver `max(collected_at)`을 **적재 완료 후에만** DONE 기록 ② 다음 실행은 watermark 이후 신규 버전만 처리 ③ **중단 방어**: 시작 시 `collected_at > watermark` 잔존행(이전 중단의 부분적재)을 **선삭제 후 재적재**(미완성 drop — PROJECT.md §3 재개 표준) |

## 2. Dim — code 테이블 정규화 (중복 row 방지)

| 테이블 | grain | 컬럼 | 소스 |
|---|---|---|---|
| `gold_dim_dataset` | (dataset) 152행 | oa_id, name_ko, service_name, fmt, major/category/sub_category, **entity_type, detail_table** | seed(taxonomy)+registry+카탈로그 |
| `gold_dim_region` | (admin_dong_code) 서울 ~425행 | admin_dong_name, legal_code, legal_dong_name, gu_code, gu_name, sido_name | bronze_ref_admin_dong |
| `gold_dim_business_status` | (fmt, status_code) | status_name, detail_status_code/name | silver history distinct — **v1/v2 코드 네임스페이스 분리(fmt)** |

> entity/history/detail 은 **코드만** 저장하고 이름(행정동명·상태명·API명)은 dim 에서 조인 — 행 중복 제거.
> 그 외 code성 반복값 발견 시 동일하게 dim 추가.

## 3. Detail — 비공통 영역 (cluster 8 + single 70 = 78, 전부 이력)

공통 규약: grain `(entity_id, collected_at, content_hash)`(**history-form** — 비공통 값 변경도 버전),
key 컬럼 = entity_id(+dataset: 파티션/필터용 중복 보관, 문서화된 비정규화) + 버전키. payload = 그
테이블의 비공통 필드(`lf()` 추출). **payload 컬럼명 = 소스 필드코드 lowercase**(추적성 — 의미역
rename(예: chaircnt→seat_count)은 후속 정제 단계). 소속 없는 필드 컬럼 없음(단독) / 클러스터는
합집합(소수 null 허용).

### 3.1 detail_cluster (명확한 겹침만 — Jaccard≥0.7 ∧ 멤버≥3 ∧ 공유≥8)

| 테이블 | 도메인(업무) | 종수 | 공유/payload | 구성 |
|---|---|---:|---|---|
| `gold_food_sanitation_business_detail` | 식품위생업(제조·판매·접객) | 21 | 19/20 | general_restaurant, rest_restaurant, bakery, food_mfg, food_additive_mfg, instant_sale_mfg, food_subdivision, food_sale_etc, food_transport, food_vending, food_cold_storage, container_pkg_mfg, edible_ice_sale, distribution_sale, hfood_dist_sale, hfood_general_sale, group_meal_facility, group_meal_food_sale, contract_meal_service, entertainment_bar, singing_bar |
| `gold_media_content_business_detail` | 미디어·콘텐츠업(영화·음반·게임제작·출판·공연) | 16 | 13/22 | cinema, film_production/distribution/import/screening, video_production/distribution, music_video_production/distribution, online_music_service, game_production/distribution, publisher, printing_shop, performance_hall, pop_culture_agency |
| `gold_tourism_business_detail` | 관광사업(여행·관광편의·야영·국제회의) | 15 | 29/31 | general/domestic/overseas_travel_agency, tour_restaurant, tour_entertainment_bar, foreigner_entertainment_bar, tourist_cabaret, tourist_performance_hall, tour_cruise, city_tour_bus, resort_complex, convention_facility/planning, general/auto_campground |
| `gold_sports_facility_detail` | 체육시설업 | 11 | 11/14 | golf_course, golf_range, fitness_center, swimming_pool, ice_rink, billiard_hall, dance_hall, dance_academy, martial_arts_gym, sled_park, yacht_marina |
| `gold_game_entertainment_venue_detail` | 게임·노래·비디오 이용업소 | 9 | 31/31 | general/youth/combined_game_arcade, internet_game_cafe, karaoke_room, video_small_theater, video_viewing_room/service, combined_video_service |
| `gold_public_sanitation_service_detail` | 공중위생영업(이·미용·목욕·세탁) | 4 | 16/22 | barber_shop, beauty_shop, bathhouse, laundry |
| `gold_medical_institution_detail` | 의료기관(의원급·법인) | 3 | 9/11 | clinic, affiliated_medical, medical_corporation |
| `gold_amusement_park_detail` | 유원시설업 | 3 | 20/28 | general/full_amusement_park, amusement_etc |

### 3.2 detail_single (고유 스키마 — 70개, API당 1테이블)

`gold_<short>_detail` 패턴. 대표: `gold_pharmacy_detail`, `gold_optical_shop_detail`,
`gold_dental_lab_detail`, `gold_lodging_detail`, `gold_postpartum_care_detail`, `gold_hospital_detail`,
`gold_animal_hospital_detail`, `gold_livestock_*_detail`(5), `gold_meter_*_detail`(4),
`gold_groundwater_*_detail`(3), `gold_tobacco_*_detail`(3), v2 환경 13종(`gold_air_pollution_facility_detail` 등).
전체 70개 목록·payload는 [gold-catalog.csv](../../gold-catalog.csv) `kind=detail_single`.

> 주의: `hospital`(병원)은 의원급 클러스터와 필드가 갈려 **단독**이다(병상/과목 등 확장 필드).
> 소형 유사군(계량기 4·지하수 3·담배 2 등)은 공유<8 → 엄격 기준에 따라 단독 유지. 완화는 카탈로그
> 임계만 조정(문서·csv 재생성).

## 4. cluster 명명 규칙 (적용됨)

sub_category/컬럼명 그대로 금지 · 포괄어(sale/info/data) 금지 · 도메인 의미 우선 · snake_case ·
"대분류_세부분류" 지향 · 이름만으로 데이터 유추 가능. 애매했던 것 후보/추천:

| 클러스터 | 후보 | 채택(추천) |
|---|---|---|
| 게임장·노래방·비디오방 9종 | game_entertainment_venue / multimedia_venue / arcade_karaoke_video_venue | **game_entertainment_venue** — 게임산업법 계열 이용업소 대표성 |
| 식품 21종 | food_sanitation_business / food_industry / food_service_mfg | **food_sanitation_business** — 식품위생법상 영업(제조~접객) 전체 포괄 |
| 미디어 16종 | media_content_business / culture_content_industry / av_media_publishing | **media_content_business** — 영화·음반·게임·출판 공통 업무 |
| 이·미용·목욕·세탁 4종 | public_sanitation_service / personal_hygiene_service | **public_sanitation_service** — 공중위생관리법 법정 도메인 |

## 5. 관계 요약

```text
gold_business_entity (supertype, 현재)
  ├─ gold_business_entity_history (entity_id, 버전)      ← silver_license_history
  ├─ gold_food_sanitation_business_detail (entity_id, 버전)
  ├─ gold_media_content_business_detail ...  (cluster 8)
  ├─ gold_pharmacy_detail / gold_hospital_detail ... (single 70)
  ├─ dataset → gold_dim_dataset (152)
  ├─ admin_dong_code → gold_dim_region (~425)
  └─ (fmt,status_code) → gold_dim_business_status
증분: gold_load_run_marker (collected_at 워터마크 + DONE + 미완성 drop)
```
