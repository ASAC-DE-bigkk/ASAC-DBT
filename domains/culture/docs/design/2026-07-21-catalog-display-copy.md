# 외부 카탈로그 전시 문구 (display 계층) — 설계

- 날짜: 2026-07-21
- 대상: culture 외부 공개 gold 7종 (`meta.external: true`)
- 배경: 카탈로그 카드가 내부 개발 문맥(이슈번호·그레인·내부 모델명)을 그대로 노출해
  외부 소비자가 데이터셋을 이해하고 가져다 쓰기 어렵다. 상품 전시면으로 재작성한다.

## 1. 문제 실측

### 1-1. 문구가 내부 언어다

```
gold_culture_activity_by_dong
  행정동(admin_dong_code) × 일자 문화활동 집계(#48). dim_admin_dong 426동 scaffold라
  활동 0건 동도 0으로 존재. sports 제외.
```

`#48`, `dim_admin_dong`, `scaffold` — 셋 다 팀 내부에서만 통하는 표현이다.

### 1-2. 설명이 중간에서 잘린다 (버그)

YAML 비인용 스칼라에서 ` #` 이후는 주석이다. 따라서

```yaml
description: 공연별 예매상황판 순위 궤적 요약(그레인 performance_id, 1공연 1행, #269). KOPIS는 …
```

는 manifest 에 `공연별 예매상황판 순위 궤적 요약(그레인 performance_id, 1공연 1행,` 까지만 실린다.
culture yml 전체 **15줄**이 이 상태다 (gold 14 + silver 1).

| 파일 | 줄 | 잘리는 대상 |
|---|---|---|
| `models/gold/_culture_gold__models.yml` | 15, 57, 64, 206, 240, 278, 291, 424, 456, 502, 515, 580, 623, 630 | 모델 5 + 컬럼 9 |
| `models/silver/_culture_silver__models.yml` | 1줄 | 컬럼 1 |

이슈번호를 걷어내면 잘림도 함께 해소된다.

## 2. 설계

### 2-1. 2계층 — `config.meta.display`

`description` 은 **내부용으로 유지**한다(그레인·산식·구현 주의). 외부 전시 문구는
`config.meta.display` 에 따로 둔다. dbt docs 와 팀 개발자는 기존 설명을 그대로 보고,
외부 카탈로그 카드만 상품 문구로 나간다.

```yaml
- name: gold_culture_dine_around
  description: "동별 문화 밀도 × 요식업 스톡 프로필(그레인 admin_dong_code, #308·티어링 v2). …"
  config:
    contract:
      enforced: true
    meta:
      external: true
      display:
        title: 문화·미식 동반 추천 지수
        summary: 동네마다 앞으로 90일간 예정된 문화행사량과 영업 중인 음식점 규모를 나란히 점수화했습니다. …
        caveat: 음식점 데이터가 연결된 동은 426곳 중 219곳입니다. …
        use_cases:
          - 데이트·나들이 코스 추천 서비스
          - 상권 입지 검토 리포트
```

| 필드 | 필수 | 용도 |
|---|---|---|
| `title` | ✅ | 카드 제목(한글 상품명). 기술 테이블명은 아래에 작게 병기 |
| `summary` | ✅ | 카드 본문 2문장 — 무엇이 들어있고 무엇에 쓰는가 |
| `caveat` | 선택 | 모르면 오해할 한계. 없으면 렌더 생략 |
| `use_cases` | ✅ | 활용 예시 2~3개 (칩 렌더) |

`caveat` 을 둔 근거: 7종 중 2종에 외부 사용자가 반드시 알아야 할 한계가 있다
(`booking_curve` = 예매율·판매좌석 원천 부재, `dine_around` = 동 커버리지 51.4%).
Q&A 트랙에서 지켜온 faithfulness 원칙(가짜 정밀도 금지)을 전시면에도 적용한다.

### 2-2. 컬럼은 2계층을 만들지 않는다

컬럼 `description` 은 **직접 정리**한다. 컬럼 설명은 원래 소비자용에 가깝고,
100여 개를 두 벌로 관리하면 반드시 어긋난다.

정리 규칙:

1. 이슈번호(`#48`, `#111`, `#282` …) 전부 제거 — 잘림 버그도 함께 해소
2. 내부 모델명(`dim_admin_dong`, `int_culture_activity_days`, `silver_culture_performance`,
   `citydata gold`) → 일반 용어로 치환
3. 출처 기관명(KOPIS·KCISA·SeMA·세종문화회관·서울시)은 **유지** — 외부에도 유용한 정보
4. 그레인·조인 키·단위·KST 표기는 **유지**, 표현만 평이하게
5. 물리 타입 주의사항은 소비자 언어로 (`물리 varchar 주의` → `문자열로 저장됩니다`)

### 2-3. 배선

```
dbt yml (config.meta.display)
   → manifest.json
   → extract.py  : display 4필드를 스냅샷 테이블 레코드에 실음
   → snapshot/catalog_snapshot.json
   → app/models.py (TableSummary·TableDetail, 전부 Optional)
   → app/static/index.html (카드·상세 드로어)
```

- `display` 가 없으면 스냅샷에 필드를 넣지 않는다 → 내부 7종과 타 도메인 100종은 **무변경**
- 화면 폴백: `display_name` 없으면 기존처럼 테이블명, `summary` 없으면 `description`
- 타 도메인이 나중에 자기 yml 에 `display` 를 달면 basic 병합 경로로 자동 반영된다

### 2-4. 렌더

| 위치 | 지금 | 바뀐 뒤 |
|---|---|---|
| 카드 제목 | `gold_culture_event_schedule` (mono) | **서울 문화행사 통합 일정** + 아래 줄에 작은 mono 테이블명 |
| 카드 본문 | 내부 description(잘린 것 포함) | `summary` |
| 상세 드로어 Description | 내부 description | `summary` → `caveat` 배너 → `use_cases` 칩 |
| 상세 드로어 컬럼표 | `#48` 섞인 설명 | 정리된 설명 |

검색(`q`) 대상에 `display_name` 과 `summary` 를 추가한다 — 한글 상품명으로도 찾아야 한다.

## 3. 전시 문구 (확정본)

### 3-1. gold_culture_event_schedule

- **title**: 서울 문화행사 통합 일정
- **summary**: 서울에서 열리는 공연·전시·축제·체험 행사를 한 행에 하나씩 모은 통합 일정표입니다. 시작일과 종료일, 장소 이름과 좌표, 자치구·행정동, 유·무료 표기가 함께 들어 있어 "이번 주말 성동구 행사" 같은 조회를 이 데이터셋 하나로 끝낼 수 있습니다.
- **caveat**: 6개 출처를 합치면서 같은 행사가 중복되지 않도록 정리했습니다. 분류(category) 값은 출처마다 체계가 달라 통합 분류가 아닙니다.
- **use_cases**: 주말 나들이 추천 서비스의 행사 목록 / 지역 문화 소식 뉴스레터 / 행사 밀집 지역 분석

### 3-2. gold_culture_activity_by_dong

- **title**: 행정동별 일자 문화활동량
- **summary**: 서울 426개 행정동에 대해 하루 단위로 문화활동이 몇 건 열리는지 집계했습니다. 공연·행사·축제·전시 등 유형별 건수와 함께 무료 행사, 교육·체험 행사 건수를 따로 제공합니다.
- **caveat**: 행사가 없는 동도 0으로 채워져 있어 지도나 시계열에 그대로 얹을 수 있습니다. 무료 여부는 서울시 문화행사 출처에만 있어 그 범위의 건수입니다.
- **use_cases**: 생활권 문화 인프라 격차 분석 / 부동산·상권 리포트의 생활편의 지표 / 동 단위 문화 히트맵

### 3-3. gold_culture_calendar_density

- **title**: 자치구 일자별 문화행사 밀도
- **summary**: 자치구마다 하루에 행사가 몇 건 열리고 그중 한 유형에 얼마나 몰리는지를 요약했습니다. 볼거리가 많은 날을 찾는 쪽과, 행사를 새로 열 때 경쟁을 피할 날을 고르는 쪽 모두가 같은 표를 씁니다.
- **caveat**: (없음)
- **use_cases**: 행사 개최일 선정 / "이번 주 볼거리 많은 자치구" 콘텐츠 / 지역별 문화 공급 편차 분석

### 3-4. gold_culture_boxoffice_daily

- **title**: 공연 예매 랭킹 (일별)
- **summary**: 공연 예매 순위를 매일 한 번 찍어 쌓은 데이터입니다. 3일 전 순위와의 변동폭, 차트 체류 일수, 신규 진입 여부까지 계산돼 있어 "요즘 뜨는 공연"을 바로 뽑을 수 있습니다.
- **caveat**: 원천이 순위만 제공합니다. 예매율·판매 좌석 수·매출액은 포함되지 않습니다.
- **use_cases**: 인기 공연 큐레이션 / 장르별 흥행 추이 리포트 / 공연 추천 모델의 인기도 피처

### 3-5. gold_culture_booking_curve

- **title**: 공연별 인기 궤적 요약
- **summary**: 공연 한 편이 예매 순위에 언제 진입해 며칠 머물렀고 최고 몇 위까지 올랐는지를 한 행으로 요약했습니다. 진입 순위와 마지막 순위가 함께 있어 상승세인지 하락세인지 바로 판단할 수 있습니다.
- **caveat**: 순위 기반 지표만 제공합니다 — 원천에 예매율·판매 좌석 수·매진 여부가 없습니다. 순위 50위 밖에 있던 기간은 집계되지 않습니다.
- **use_cases**: 공연 마케팅 성과 벤치마킹 / 흥행 예측 모델 입력 / 장르별 인기 수명주기 비교

### 3-6. gold_culture_event_crowd

- **title**: 행사 지역 요일·시간대 혼잡도
- **summary**: 문화행사가 열리는 자치구가 요일과 시간대별로 평소 얼마나 붐비는지에 대한 기준선입니다. 서울시 실시간 도시데이터의 인구·혼잡 관측을 요일×시간 칸으로 모아 평균 인구와 대표 혼잡 등급을 계산했습니다.
- **caveat**: 특정 행사 당일의 증가분이 아니라 평상시 패턴입니다. 서울시가 관측하는 주요 지점 기준이라 자치구 전역을 대표하지는 않습니다.
- **use_cases**: 방문 시간대 추천 / 행사 운영 인력·안전 배치 계획 / 한적한 관람 시간 안내

### 3-7. gold_culture_dine_around

- **title**: 문화·미식 동반 추천 지수
- **summary**: 동네마다 앞으로 90일간 예정된 문화행사량과 영업 중인 음식점 규모를 나란히 점수화했습니다. 두 값이 모두 높은 동네일수록 점수가 높아 "공연 보고 밥 먹기 좋은 동네" 정렬에 그대로 쓸 수 있습니다.
- **caveat**: 음식점 데이터가 연결된 동은 426곳 중 219곳입니다. 나머지 동은 문화 지표만 채워지고 점수는 비어 있습니다(has_dining_data 로 구분).
- **use_cases**: 데이트·나들이 코스 추천 / 상권 입지 검토 / 지역 관광 코스 설계

## 4. 컬럼 설명 정리 (before → after)

변경이 필요한 컬럼만 적는다. 나머지(`performance_name` = 공연명 등)는 그대로 둔다.

### 4-1. gold_culture_activity_by_dong

| 컬럼 | after |
|---|---|
| `admin_dong_code` | 행정동 코드 — 행정안전부 표준 10자리. 다른 행정동 데이터와 붙이는 조인 키 |
| `stat_region_cd` | 통계청 집계구 코드 — 통계청 인구·가구 통계와 붙일 때 사용 |
| `event_date` | 활동 일자(KST). 여러 날에 걸친 행사는 날짜마다 한 행으로 펼쳐진다 |
| `activities_count` | 그날 그 동에서 열린 전체 문화활동 수 — 아래 유형별 건수의 합 |
| `free_events_count` | 그날 그 동의 무료 문화행사 수. 유·무료 표기는 서울시 문화행사 출처에만 있어 그 범위의 건수 |
| `edu_experience_events_count` | 그날 그 동의 교육·체험 분류 행사 수 |

### 4-2. gold_culture_booking_curve

| 컬럼 | after |
|---|---|
| `performance_id` | KOPIS 공연 식별자(mt20id) — 공연 한 편당 하나, 이 표의 기본 키 |
| `best_rank` | 이력 중 가장 높았던 순위(숫자가 작을수록 상위, 1이 최상위) |
| `days_on_chart` | 예매 순위표에 등장한 누적 일수 — 체류 기간 |
| `days_to_peak` | 첫 등장부터 최고 순위에 도달하기까지 걸린 일수 |

### 4-3. gold_culture_boxoffice_daily

| 컬럼 | after |
|---|---|
| `snapshot_date` | 순위를 집계한 날(YYYY-MM-DD). 문자열로 저장된다 |
| `performance_id` | KOPIS 공연 식별자(mt20id) — 공연 상세 정보와 붙이는 조인 키 |
| `gu_code` | 공연장이 속한 자치구 코드 |
| `rank_prev_3d` | 3일 전 같은 공연의 순위. 그때 순위표에 없었으면 비어 있다 |
| `rank_delta_3d` | 순위 상승폭(3일 전 순위 − 오늘 순위). 양수면 상승, 비어 있으면 신규 또는 재진입 |
| `days_on_chart` | 이 공연이 순위표에 등장한 누적 일수(오늘 포함) |
| `is_new_entry` | 어제는 없다가 오늘 진입했는지 여부(첫 진입·재진입 공통) |

### 4-4. gold_culture_calendar_density

| 컬럼 | after |
|---|---|
| `gu_code` | 자치구 코드 |
| `event_date` | 활동 일자(KST). 여러 날에 걸친 행사는 날짜마다 한 행으로 펼쳐진다 |
| `total_events` | 그날 그 구에서 열린 전체 문화활동 수 — "볼 게 많은 날" 지표 |
| `busiest_type_count` | 가장 많이 열린 유형의 행사 수 — 같은 유형끼리의 경쟁 규모 |

### 4-5. gold_culture_event_crowd

| 컬럼 | after |
|---|---|
| `gu_code` | 자치구 코드 — 혼잡 관측과 행사 데이터를 잇는 공통 키 |
| `gu` | 자치구 이름 |
| `day_of_week` | 요일(1=월요일 … 7=일요일) |
| `hour_of_day` | 시각(0~23, KST). 최근 18일 관측을 요일×시각 칸으로 모아 계산했다 |
| `avg_ppltn` | 그 시간대 그 자치구 주요 지점의 평균 실시간 인구(명) |
| `avg_congest_score` | 평균 혼잡 점수(여유 1 · 보통 2 · 약간 붐빔 3 · 붐빔 4). 높을수록 붐빈다 |
| `crowd_samples` | 계산에 사용한 관측 건수 — 값이 클수록 신뢰도가 높다 |

### 4-6. gold_culture_event_schedule

| 컬럼 | after |
|---|---|
| `event_ref` | 행사 고유 키. 출처 접두어가 붙는다(예 `performance:12345`) |
| `event_type` | 행사 출처 유형 — 목록에서 아이콘·필터로 쓰기 좋은 축 |
| `event_at` | 행사 시작 시각(KST) — 기간 조회의 표준 필터 컬럼 |
| `gu_code` | 자치구 코드 |
| `admin_dong` | 행정동 이름. quality_status 가 dong_precise 일 때만 신뢰할 수 있다 |
| `admin_dong_code` | 행정동 코드 — 행정안전부 표준 10자리 |
| `quality_status` | 위치 정밀도 — dong_precise(행정동까지 확정) / gu_only(자치구까지) / unmatched(미확정) |

### 4-7. gold_culture_dine_around

| 컬럼 | after |
|---|---|
| `admin_dong_code` | 행정동 코드 — 행정안전부 표준 10자리. 이 표의 기본 키 |
| `gu_code` | 자치구 코드 |
| `performances_upcoming_90d` | 앞으로 90일간 예정된 공연 수 |
| `dining_active_cnt` | 영업 중인 음식점 수(식품 인허가 기준). 음식점 데이터가 연결되지 않은 동은 비어 있다 |
| `dining_opened_365d` | 최근 365일간 새로 문을 연 음식점 수 — 상권 활력 지표 |
| `has_dining_data` | 음식점 데이터가 연결된 동인지 여부. false 면 음식점 관련 값과 점수가 모두 비어 있다 |
| `culture_events_pctl` | 426개 동 중 문화행사량 백분위(0~1, 클수록 상위) |
| `dining_stock_pctl` | 음식점 데이터가 있는 219개 동 중 음식점 수 백분위(0~1) |
| `dine_around_score` | 문화 백분위와 음식점 백분위의 기하평균(0~1). 둘 다 높아야 점수가 높다 |

## 5. 잘림 버그 수정

외부 7종 밖의 잘린 줄도 같은 PR 에서 고친다. 방법은 두 가지 중 하나:

- 이슈번호를 뺄 수 있으면 뺀다 (외부 7종 컬럼은 대부분 여기 해당)
- 내부 문맥이라 남겨야 하면 **설명 전체를 큰따옴표로 감싼다**

대상: `_culture_gold__models.yml` 14줄 + `_culture_silver__models.yml` 1줄.
내부 마트(slo_daily·qa_eval·venue_profile·sports_schedule 등)의 설명은 문구를 바꾸지 않고
따옴표만 씌워 원문이 온전히 실리게 한다.

## 6. 검증

| # | 검증 | 통과 기준 |
|---|---|---|
| 1 | `dbt parse` 후 manifest 조회 | 외부 7종에 `config.meta.display` 4필드 존재 |
| 2 | 잘림 회귀 검사 | culture 전 모델·컬럼 description 중 `,` 또는 `(` 로 끝나는 것 0건 |
| 3 | `extract.py` 재실행 | 스냅샷에서 display 필드 보유 테이블 = 정확히 7개, 나머지 107개는 필드 없음 |
| 4 | API | `/api/v1/catalog/tables` 응답에 `display_name`·`summary`·`caveat`·`use_cases` 노출 |
| 5 | 화면 | 카드 7종 한글 제목 렌더, caveat 배너 2종, use_cases 칩, 콘솔 에러 0 |
| 6 | 폴백 | 내부 7종·타 도메인 카드가 기존과 동일하게 렌더 |

## 7. 범위 밖

- 내부 7종(`slo_daily`·`qa_eval`·`venue_profile`·`sports_schedule`·`reservation_daily`·
  `movie_boxoffice_daily`·`location_daily`) 의 전시 문구 — 외부에 나가지 않는다
- 타 도메인 100종 — 각 도메인 소유자 몫. 구조만 열어 둔다
- 영문 번역 — 필요해지면 `display.title_en` 등으로 확장 가능한 구조

## 8. PR 구성

| 순서 | 레포 | 내용 |
|---|---|---|
| 1 | ASAC-DBT | display 블록 7개 + 컬럼 설명 정리 + 잘림 15줄 + 이 문서 |
| 2 | ASK-Seoul-Dashboard | extract 병합 + 응답 모델 4필드 + 카드·드로어 렌더 + 검색 대상 확장 |

2번은 1번이 dev 에 머지된 뒤 manifest 를 다시 뽑아야 실측할 수 있다.
