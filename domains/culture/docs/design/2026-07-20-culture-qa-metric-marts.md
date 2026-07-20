# Q&A metric 마트 1차 — venue_profile 신규 + activity_by_dong·event_crowd 확장

2026-07-20 · culture 도메인 · 로드맵 #269 후속 (Q&A 트랙)

## 배경 / 왜

페르소나 Q&A는 **governed** 원칙을 따른다: 답이 정의된 metric(gold 마트)을 통해서만 나와
LLM이 dedup 누락·야구 포함 같은 판단 실수를 할 수 없게 한다. 티어링
(`ask-seoul/culture-gold-marts-tiering.tsv`)에서 Q&A 가치 高로 채점됐지만 마트가 없어
답하지 못하는 질문이 남아 있다:

- "그 공연장 어떤 곳이야" (#18 venue_profile)
- "그 공연장(지역) 언제 가면 한적해" (#21 venue_crowd_baseline)
- "아이랑 갈 무료 문화행사" (#19 free_access)

원안(신규 마트 3개)은 셀프 크리틱에서 수정됐다:

| 원안 | 문제 | 수정 |
|---|---|---|
| venue_crowd_baseline 신규 (facility×요일×시간) | citydata가 gu 단위 → 같은 구 시설 전부 동일값 복제(1,689×7×24≈28만 행, 고유정보 4,008행). 시설 단위처럼 보이는 구 단위 답 = faithfulness 결함(lastmile_bike 폐기 사유와 동일) | **event_crowd v2로 축소**: 기존 마트에 요일 축 추가 (gu×요일×시간) |
| free_access 신규 (동별 지수) | ① 질문("행사 목록")과 그레인("동 지수") 불일치 ② 티어링 처분권고 자체가 "activity_by_dong 흡수" ③ family_friendly 휴리스틱·access_score 매직넘버 = governed 위반 | **activity_by_dong에 additive 컬럼 2개로 흡수**. 행사 목록 질문은 event_schedule의 기존 is_free로 이미 답 가능 |
| venue_profile 신규 | 타당하나 주소·좌표 누락 + 커버리지 미실측 | 유지 + address·lat·lon 추가 + 선실측 완료 |

## 선실측 (dev, 7/20)

- **시설-공연 링크**: 시설 1,689 중 공연 링크 421(24.9%). 공연 1,887 중 링크 1,886(**99.9%**).
  → 공연 통계는 421개 시설만 채워짐(나머지 perf_count=0), 링크 품질은 견고.
- **시설 dim 충전율**: address 1,689/1,689(100%) · lat/lon 100% · seat_scale 1,076/1,689(63.7%).
- **crowd 요일 밀도**: gu×요일×시간 4,008셀, 셀당 min 9 / **p50 66** / max 648, 샘플<3 셀 **0%**.
  → 요일 축은 통계적으로 성립 (18일 이력이지만 구별 핫스팟 다수 × 시간별 수집 덕).
- **event_schedule is_free**: 이미 노출됨. event 소스 18,025/18,032 충전(무료 12,246).
  타 소스(sejong·performance·exhibition·kcisa)는 원천에 유무료 정보 없음 → null (정직한 상태).
- **silver_culture_event.is_free** 값: `무료` 12,569 / `유료` 6,987 / null 8. 술어 = `is_free = '무료'`.
- **category 최대값**: `교육/체험` 6,332건 — 기술적(descriptive) 카운트로 노출할 가치 있음.

## 설계

### A. `gold_culture_venue_profile` — 신규

- **질문**: "그 공연장 어떤 곳이야"
- **그레인**: `facility_id` (시설 1행, 1,689행)
- **소스**: `silver_culture_facility`(dim: 이름·주소·좌표·규모·행정동) LEFT JOIN
  `silver_culture_performance` 집계(facility_id 기준)
- **컬럼**:

| 컬럼 | 타입 | 정의 |
|---|---|---|
| facility_id | varchar | KOPIS mt10id (PK, not_null+unique) |
| facility_name | varchar | 시설명 |
| address | varchar | 주소 (충전 100%) |
| latitude / longitude | double | 좌표 (충전 100%) |
| seat_scale | integer | 좌석 규모 (충전 63.7%, null 허용) |
| gu / gu_code / admin_dong / admin_dong_code | varchar | 공간축 canonical |
| perf_count | integer | KOPIS 공연수 (링크 없으면 0) |
| distinct_genres | integer | 장르 수 |
| top_genre | varchar | 최다 장르 (max_by, 공연 없으면 null) |
| top_genre_count | integer | 최다 장르 공연수 |
| first_perf_date / last_perf_date | date | 공연 기간 범위 |
| quality_status | varchar | facility dim의 quality_status 전파 |

- **캐비앳(모델 주석·yml description)**: 공연 통계는 **KOPIS 공연 기준**(전시·축제·행사 미포함).
  좌석·위치는 전 시설 충전.
- **contract enforced** + `meta.external: false` — 티어링 "외부 제외, Q&A 메트릭". 대시보드
  external 플래그 메커니즘(meta 우선, INTERNAL_GOLD 폴백)의 **첫 meta 실사용**.
- **테스트**: not_null·unique(facility_id) + 불변식 singular test
  (perf_count>=0, perf_count=0 → top_genre null 단방향 — genre 자체가 null인 공연 존재 가능, first<=last).

### B. `gold_culture_activity_by_dong` — additive 확장

- **질문**: "우리 동네 무료(·교육/체험) 문화행사 얼마나" — 동별 롤업.
  행사 **목록** 질문("아이랑 갈 무료 행사 뭐 있어")은 event_schedule 기존
  `is_free`·`category` 필터가 담당(추가 작업 없음).
- **그레인 불변**: admin_dong_code × event_date. 기존 컬럼 불변.
- **추가 컬럼 2개** (event 소스에서만 파생 — 타 소스는 유무료 정보 없음):

| 컬럼 | 타입 | 정의 |
|---|---|---|
| free_events_count | bigint | 해당 동×일 `is_free='무료'` event 건수 |
| edu_experience_events_count | bigint | 해당 동×일 `category='교육/체험'` event 건수 |

- **명명 원칙**: `family_friendly` 같은 해석적 이름 대신 **있는 그대로 기술**.
  "가족 적합" 해석은 Q&A 레이어 몫 (governed — 마트는 사실만).
- 합성 지수(access_score)·가중치 없음 — 원시 카운트만.
- **계약**: 컬럼 2개 additive 추가 (비파괴). 테스트: free<=events_count 불변식.

### C. `gold_culture_event_crowd` — v2 (요일 축)

- **질문**: "그 행사 지역, **무슨 요일** 몇 시가 한적해" — v1(gu×시간)이 못 답하던 요일 차원.
- **그레인 변경(파괴적)**: `gu_code × hour_of_day`(576행) → `gu_code × day_of_week × hour_of_day`(~4,008행).
- **추가 컬럼**: `day_of_week` (integer 1–7, Trino `day_of_week()` = 월1…일7).
  기존 컬럼(avg_ppltn·avg_congest_score·typical_congest·crowd_samples)은 정의 동일, 셀만 세분화.
- **정당화**: 외부 공개 마트의 그레인 변경이지만 카탈로그 공개 직후(외부 소비자 실질 0)라
  지금이 마지막 적기. PR에 그레인 변경 명시. 셀당 p50 66샘플로 통계적 성립 실측 완료.
- **계약**: yml 그레인 설명 갱신 + day_of_week 컬럼 추가. 테스트: 불변식 singular
  (dow 1–7, hour 0–23, crowd_samples>0) 갱신.

## 스코프 밖

- `qa_eval`(#20): 라우팅 대상 마트 확보 후 별도 세션 (이번 스코프 결정대로).
- `weather_fit`(#13): weather gold Iceberg 미게시(#268) 하드차단.
- event_schedule·silver 변경: 없음 (is_free 이미 노출).
- 대시보드(ASK-Seoul-Dashboard) 변경: 없음 — venue_profile은 meta.external=false로 자동 내부 분류
  (PR#6 merge 후 extract 재실행 시 반영).

## 구현·검증 방식

기존 4마트 세션과 동일 패턴:
1. 마트별 이슈(org 템플릿) + 브랜치 → 모델 + contract yml + 테스트
2. ASAC-DBT push → 컨테이너(sample/dbt) `git checkout --detach origin/<branch>` → `dbt build --select <model> <tests>` → dev 복귀
3. AC 실측치 PR body 기재, base dev
4. A·B·C는 서로 다른 파일이라 병렬 브랜치 가능하나, yml 인접 편집 충돌 예방 위해 **순차 진행**(A→B→C)

## AC (수용 기준)

- A: 1,689행(시설 전량), perf_count>0 행 = 421, address/lat/lon not_null 100%, 계약 PASS
- B: 그레인·기존 컬럼 불변(행수 동일), free_events_count 합계 > 0, 계약 PASS
- C: ~4,008행, dow 1–7 전체 존재, 셀당 crowd_samples min>=1, 계약 PASS
- 공통: 컨테이너 dev `dbt build` 전체 PASS, 문서(-plan.md 쌍) 갱신
