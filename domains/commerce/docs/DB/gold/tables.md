# DB/gold — 테이블 명세 (Supertype/Subtype + code 정규화 + 이력)

**물리 위치(확정)**: gold 는 **외부 서빙 DB = PostgreSQL**(sample docker compose 의 전용 컨테이너
`serving-postgres`)에 구축한다. Iceberg(Trino) 스택은 raw~silver 용으로 기존 그대로(별도 1개) 유지 —
gold 적재기가 Trino(silver 읽기) → Postgres(gold 쓰기)로 흘린다.

gold = silver(이력 원천)를 **정규화해 DB에 증분 적재**하는 서빙 레이어. 구조는 **Supertype(공통
entity) / Subtype(상세 detail)**: 모든 API 데이터는 먼저 `commerce_business_entity`에 들어가고,
비공통 영역은 detail 테이블이 `entity_seq`로 매핑한다(공통 컬럼 재저장 없음). code성 값(행정동/상태/
데이터셋)은 dim으로 분리. **카탈로그도 DB 객체**(`commerce_catalog`)로 존재해 DDL·적재를 구동한다.

**entity_seq(정수 서러게이트, 2026-07-10 개정)**: 식별키를 sha256 해시(text 64자)에서 **bigint
시퀀스**로 전환했다 — 85개 테이블 전체의 PK/FK·조인이 이 키를 물기 때문에 8byte 정수가 조인/인덱스
비용에서 명확히 유리하고, 해시가 주던 "무조율 독립 계산" 장점은 gold 가 일 1회 배치 적재라 실제로
쓰이지 않았다. 자연키(`dataset,opnsfteamcode,mgtno`) → `entity_seq` 매핑은 `commerce_entity_key`
(bigserial, 영구 테이블)가 담당 — **재적재/초기화에서도 항상 보존**해야 같은 업소가 같은 번호를
유지한다(자연키는 entity 컬럼으로 그대로 남아 소스 식별성은 보존 — CLAUDE.md §2.1 정합).
근거 문서: [normalization-plan.md](normalization-plan.md), [partitioning-indexing-plan.md](partitioning-indexing-plan.md).

**명명 규칙(확정)**: 객체명에 레이어(gold)를 넣지 않는다 — 레이어는 DB/스키마가 식별한다. 대신
**`commerce_` 접두로 도메인을 식별**한다(타 도메인과 같은 DB를 쓰더라도 구분).

전체 카탈로그(payload 컬럼 포함): [../../gold-catalog.csv](../../gold-catalog.csv) · 조회는 view
([views.md](views.md)) 우선 · 적재 DAG: §6.

## 1. Core — Supertype + 이력 + marker

### commerce_entity_key (자연키 → entity_seq 영구 매핑)

| 항목 | 값 |
|---|---|
| grain | `(dataset, opnsfteamcode, mgtno)` — 업소 자연키 1행 |
| PK | `entity_seq` bigserial(발급 후 불변) |
| 규칙 | 최초 등장 시 발급, 이후 조회만(ON CONFLICT DO UPDATE...RETURNING 으로 신규/기존 모두 1왕복). **gold 재적재·초기화에서 항상 보존** — 지우면 같은 업소가 다음 적재 때 다른 번호를 받아 정합성이 깨진다 |

### commerce_business_entity (공통 supertype — 현재)

| 항목 | 값 |
|---|---|
| grain | `(entity_seq)` — 업소 1행(현재 상태) |
| PK | `entity_seq` bigint(`commerce_entity_key` 발급) — 조인·인덱스 비용이 sha256 text 대비 낮음 |
| 소스 | `silver_license_current` |

| 컬럼 | 설명 |
|---|---|
| entity_seq | PK(위 규칙) |
| dataset, opnsfteamcode, mgtno | 자연키(원 API 식별, 그대로 컬럼 보존) — dataset → `commerce_dim_dataset` |
| **entity_type, detail_table** | 어느 detail 로 연결되나(분기 지시자 — 카탈로그가 부여) |
| business_name | 상호(bplcnm) |
| status_code, detail_status_code | 영업상태 코드 → `commerce_dim_business_status` |
| opened_at, closed_at | 인허가일/폐업일 |
| road_address, jibun_address | 주소 |
| **gu_code(=시군구코드), legal_code, admin_dong_code** | 지역 코드 → `commerce_dim_region`. **타 도메인 데이터와의 위치 매핑 키**(시군구·행정동 코드) |
| longitude, latitude | WGS84 좌표 |
| **updatedt, updatedt_ts, lastmodts_ts** | 원천 **업데이트 일자**(+파싱 ts) — **시간 조건문 기준 컬럼** |
| first_collected_at, last_collected_at, content_hash | 수집 계보/현재 버전 |

### commerce_business_entity_history (공통 변경 이력 — 별도 이력 테이블)

| 항목 | 값 |
|---|---|
| grain | `(entity_seq, collected_at, content_hash)` — **값 변경 = 버전 1행** |
| 소스 | `silver_license_history`(append-only) 정규화 |
| 컬럼 | entity_seq + 버전키 + 공통 속성(dataset/상호/상태코드/주소/**지역코드(gu·legal·admin_dong)**/좌표/**updatedt·updatedt_ts·lastmodts_ts**/일자/observed_date) |

> **지역 코드 계보(법정동→행정동 매핑)**: silver `ref_legal`/`ref_admin`/`dong` CTE 가 지번 동 토큰을
> **법정동 우선 매치 → 행정동 상호 보완**으로 채운다(법정동 1개가 행정동 여러 개에 걸치면 결정적
> 근사 — 번지 없인 정확 배정 불가). gold 는 이 결과 코드를 그대로 승계하며 **재매핑하지 않는다.**
> 마스킹 주소(`*`)는 동 코드 null(구 수준까지만) — 크로스도메인 조인 시 null 허용 설계 필요.

### commerce_load_run_marker (증분 지시자)

| 항목 | 값 |
|---|---|
| grain | `(model_name)` — gold DB 상주(레이어는 DB가 식별) |
| 컬럼 | model_name, **watermark_collected_at**, status('DONE'), rows_loaded, marked_at |
| 규칙 | ① 각 객체는 반영한 silver `max(collected_at)`을 **적재 완료 후에만** DONE 기록 ② 다음 실행은 watermark 이후 신규 버전만 ③ **중단 방어**: 시작 시 `collected_at > watermark` 잔존행(이전 중단의 부분적재) **선삭제 후 재적재**(미완성 drop — 재개 표준) |

## 2. commerce_catalog — 카탈로그의 DB 실체

gold는 "카탈로그를 만들고, 그 카탈로그로 테이블을 만든다"가 전제이므로 **카탈로그와 DB가 함께
존재**한다. `build_catalog` task(§6)가 갱신하고, 적재 task가 이걸 읽어 DDL·적재를 구동한다.

| 항목 | 값 |
|---|---|
| grain | `(object)` — 1행 = 테이블/뷰 1객체 |
| 컬럼 | object, kind(core/dim/detail_cluster/detail_single/view_*/marker/catalog), grain, members, key_columns, payload_columns, source, **catalog_version, measured_at** |
| 소스 | 152종 필드 실측(적재된 bronze `record_json` 키 — Trino) + 클러스터 규칙 + 명명맵 |
| 드리프트 | 신규 API/필드 발견 시 catalog_version 증가 + 리포트 경고(스키마 드리프트 감지) |

## 3. Dim — code 테이블 정규화 (중복 row 방지)

| 테이블 | grain | 컬럼 | 소스 |
|---|---|---|---|
| `commerce_dim_dataset` | (dataset) 152행 | oa_id, name_ko, service_name, fmt, major/category/sub_category, **entity_type, detail_table** | seed(taxonomy)+registry+카탈로그 |
| `commerce_dim_region` | (admin_dong_code) 서울 ~425행 | admin_dong_name, legal_code, legal_dong_name, gu_code, gu_name, sido_name | bronze_ref_admin_dong |
| `commerce_dim_business_status` | (fmt, status_code) | status_name, detail_status_code/name | silver history distinct — **v1/v2 코드 네임스페이스 분리(fmt)** |

> entity/history/detail 은 **코드만** 저장하고 이름(행정동명·상태명·API명)은 dim 에서 조인.
> 그 외 code성 반복값 발견 시 동일하게 dim 추가.

### 3.1 commerce_code_value (정규화 Option 1 — 공유 코드 테이블)

detail payload 의 저카디널리티 통제어휘 컬럼(예: `uptaenm`(업태명))을 **detail 스키마는 바꾸지 않고**
값 목록만 문서화/거버넌스용으로 모은 참조 테이블. 후보가 몇 개든 신규 테이블은 이 1개뿐(테이블 폭증
방지 — 근거: [normalization-plan.md](normalization-plan.md)).

| 항목 | 값 |
|---|---|
| grain | `(domain, value)` — domain = `"<detail 테이블>.<컬럼>"` |
| 컬럼 | domain, value(자연키 — 서러게이트 코드 미발급), n_occurrences(집계 시점 등장 행수, 참고용) |
| 채움 | `commerce_load_gold` DAG `build_code_values` task — `load_gold` 이후(detail 실데이터 필요) |
| 대상 | 실측 카디널리티 + **실제 값 표본 검증**을 통과한 72쌍(`include/gold/code_values.py` `CANDIDATES`) — 상수(distinct=1)·결측·0/1 플래그·동일 필드명이라도 준자유텍스트(예: `mail_order_sale.uptaenm`)는 제외 |

## 3.2 인덱스 — view-구성 요소 + 검색/이력 공통축 (2026-07-10)

### entity/history — `ddl.create_index_sql()` (17개: 2테이블×8 + entity 전용 1)

① **뷰 정의(JOIN/WHERE)가 실제로 쓰는 컬럼**(근거: [partitioning-indexing-plan.md](partitioning-indexing-plan.md),
EXPLAIN 실측) + ② **검색·조건 단위로 쓰기 좋고 이력과 연결되는 공통축**(위치코드·시간축·자연키 —
사용자 지시). detail↔entity 조인은 detail 기존 PK(entity_seq, collected_at, content_hash)로 이미
충분해 이 목록엔 없음.

| 테이블 | 인덱스 | 근거 |
|---|---|---|
| `commerce_business_entity`, `_history` | `(dataset)` | API view `where e/h.dataset = '<short>'` |
| `commerce_business_entity`, `_history` | `(admin_dong_code)` | `_DIM_JOIN` → `commerce_dim_region` 조인(행정동) |
| `commerce_business_entity`, `_history` | `(status_code, detail_status_code)` | `_DIM_JOIN` → `commerce_dim_business_status` 조인 |
| `commerce_business_entity`, `_history` | `(legal_code)` | 법정동 코드 — 위치 매핑 검색축 |
| `commerce_business_entity`, `_history` | `(updatedt_ts)` | 원천 업데이트 시각 — 시간 조건문 |
| `commerce_business_entity`, `_history` | `(lastmodts_ts)` | 최종 수정 시각(=moddt) — 시간 조건문 |
| `commerce_business_entity`, `_history` | `(opened_at)`, `(closed_at)` | 인허가/폐업일(=opendate/closedate) |
| `commerce_business_entity` | `(opnsfteamcode, mgtno)` | 자연키(=id) — entity_seq 몰라도 업소 직접 조회. `commerce_business_entity_history` 는 이 두 컬럼을 안 담아(HISTORY_COLUMNS) 대상 아님 |

### detail(78개) — `ddl.create_detail_index_sql()` (자동, 2026-07-10 실측 401개)

새 API 가 카탈로그에 추가돼도 **payload 컬럼명 접미사**로 자동 인덱싱된다(수동 목록 유지 불필요) —
`commerce_load_gold` 의 `build_catalog`→`load_gold` DDL ensure 단계에서 카탈로그 갱신 시 자동 반영.

| 접미사 | 의미(예시) | 자동 인덱싱 |
|---|---|---|
| `ymd`·`dt`·`date` | 종료/시작/취소/보험 일자(예: 종업원수·평수 문서의 moddt/opendate/closedate 류가 API마다 이런 형태로 존재) | ✅ |
| `no`·`num`·`seqno`·`asgnno` | 등록번호·지정번호(=id) | ✅ |
| `cnt`·`epcnt`·`area`·`yarea`·`scp`·`tons`·`flr` | 종업원수·면적(평수)·규모·톤수·층수 | ✅ |
| `nm`·`se`·`senm`·`gbn`·`gbnnm` | 업태명 등 명칭/구분(값 자체가 목적) | ❌ 정규화 대상([normalization-plan.md](normalization-plan.md) — `commerce_code_value`) |

실측(2026-07-10, 78테이블/725 payload 컬럼): **401개 매칭**(테이블당 평균 5.1개, 대부분 결측 위주
희소 컬럼이라 실제 인덱스 크기는 작음). 텍스트 컬럼 그대로 인덱싱(원문 보존 원칙 유지 — CAST 안 함)
이라 수량류는 **정확한 값 조회는 되지만 숫자 범위 정렬은 텍스트 기준**이라는 한계가 있다(예:
`'10' < '9'`). 범위 정렬이 필요해지면 그때 타입 컬럼 추가를 검토한다.

## 4. Detail — 비공통 영역 (cluster 8 + single 70 = 78, 전부 이력)

공통 규약: grain `(entity_seq, collected_at, content_hash)`(**history-form**), key = entity_seq(+dataset:
파티션/필터용, 문서화된 비정규화) + 버전키. payload = 비공통 필드(`lf()` 추출). **payload 컬럼명 =
소스 필드코드 lowercase**(추적성 — 의미역 rename은 후속 정제).

### 4.1 detail_cluster (명확한 겹침만 — Jaccard≥0.7 ∧ 멤버≥3 ∧ 공유≥8)

| 테이블 | 도메인(업무) | 종수 | 공유/payload |
|---|---|---:|---|
| `commerce_food_sanitation_business_detail` | 식품위생업(제조·판매·접객) | 21 | 19/20 |
| `commerce_media_content_business_detail` | 미디어·콘텐츠업(영화·음반·게임제작·출판·공연) | 16 | 13/22 |
| `commerce_tourism_business_detail` | 관광사업(여행·관광편의·야영·국제회의) | 15 | 29/31 |
| `commerce_sports_facility_detail` | 체육시설업 | 11 | 11/14 |
| `commerce_game_entertainment_venue_detail` | 게임·노래·비디오 이용업소 | 9 | 31/31 |
| `commerce_public_sanitation_service_detail` | 공중위생영업(이·미용·목욕·세탁) | 4 | 16/22 |
| `commerce_medical_institution_detail` | 의료기관(의원급·법인) | 3 | 9/11 |
| `commerce_amusement_park_detail` | 유원시설업 | 3 | 20/28 |

멤버 구성(API 목록)은 [gold-catalog.csv](../../gold-catalog.csv) `kind=detail_cluster`.

### 4.2 detail_single (고유 스키마 — 70개, API당 1테이블)

`commerce_<short>_detail` 패턴: `commerce_pharmacy_detail`, `commerce_hospital_detail`,
`commerce_optical_shop_detail`, `commerce_dental_lab_detail`, `commerce_lodging_detail`,
`commerce_postpartum_care_detail`, `commerce_livestock_*`(5), `commerce_meter_*`(4),
`commerce_groundwater_*`(3), v2 환경 13종 등. 전체 70개·payload: catalog `kind=detail_single`.

> `hospital`(병원)은 의원급 클러스터와 필드가 갈려 **단독**. 소형 유사군(계량기·지하수·담배)은
> 공유<8 → 엄격 기준상 단독 유지(완화는 카탈로그 임계만 조정).

## 5. cluster 명명 규칙 (적용됨)

sub_category/컬럼명 그대로 금지 · 포괄어(sale/info/data) 금지 · 도메인 의미 우선 · snake_case ·
이름만으로 데이터 유추 가능. 애매했던 것 후보/추천:

| 클러스터 | 후보 | 채택(추천) |
|---|---|---|
| 게임장·노래방·비디오방 9종 | game_entertainment_venue / multimedia_venue / arcade_karaoke_video_venue | **game_entertainment_venue** |
| 식품 21종 | food_sanitation_business / food_industry / food_service_mfg | **food_sanitation_business** — 식품위생법상 영업 전체 |
| 미디어 16종 | media_content_business / culture_content_industry / av_media_publishing | **media_content_business** |
| 이·미용·목욕·세탁 4종 | public_sanitation_service / personal_hygiene_service | **public_sanitation_service** — 공중위생관리법 도메인 |

## 6. 적재 DAG — commerce_load_gold (4 task)

silver(05:00) 이후 실행.

```text
commerce_load_gold (@daily, silver 이후)
  build_catalog ──> load_gold ──> build_code_values ──> report_gold
```

| task | 동작 |
|---|---|
| **`build_catalog`** | ① 적재된 bronze `record_json` 키를 dataset별 실측(Trino — 적재분 기준 권위) ② 엄격 클러스터 규칙(0.7∧3∧8) + 도메인 명명맵 적용 ③ `commerce_catalog` 갱신(catalog_version/measured_at) ④ 직전 대비 **드리프트(신규 API/필드) 감지 → 리포트 경고** |
| **`load_gold`** | ① **task 초기: DDL ensure** — catalog 를 읽어 **없는 table/view 를 생성**(CREATE IF NOT EXISTS: entity_key·core·인덱스·dim·detail 78·code_value·view 320·marker) ② marker(`watermark_collected_at`) 읽기 ③ **중단 방어**: watermark 이후 잔존행 선삭제 ④ silver history/current 의 **신규 버전만** entity/entity_history/detail/dim 에 증분 적재(자연키→`entity_seq` 는 `commerce_entity_key` 조회/발급) ⑤ 전 객체 성공 후 marker DONE |
| **`build_code_values`** | detail 실데이터 기준으로 `commerce_code_value`(정규화 §3.1) 갱신 — domain 단위 delete+insert(멱등) |
| **`report_gold`**(all_done) | 실행시간 + 카탈로그 + 객체별 적재행 Discord 리포트(#218) |

- 재적재: marker 리셋(또는 테이블 drop) → 카탈로그 기반 DDL 재생성 + silver 에서 시간순 전체 재적재
  (레이어 재적재 계약과 정합).
- 신규 데이터셋: 실측에 새 API 등장 → catalog 에 detail/view 행 추가 → 다음 load_gold 가 DDL 자동 생성.

## 7. 관계 요약

```text
commerce_entity_key ((dataset,opnsfteamcode,mgtno) -> entity_seq, 영구 보존)
commerce_catalog (DDL·적재 구동)
commerce_business_entity (supertype, 현재, PK=entity_seq)
  ├─ commerce_business_entity_history (entity_seq, 버전)      ← silver_license_history
  ├─ commerce_food_sanitation_business_detail … (cluster 8)  ← entity_seq 매핑
  ├─ commerce_pharmacy_detail / commerce_hospital_detail … (single 70)
  ├─ dataset → commerce_dim_dataset (152)
  ├─ admin_dong_code → commerce_dim_region (~425)
  └─ (fmt,status_code) → commerce_dim_business_status
commerce_code_value (정규화 참조 — detail 저카디널리티 값 72도메인)
증분: commerce_load_run_marker (collected_at 워터마크 + DONE + 미완성 drop)
```
