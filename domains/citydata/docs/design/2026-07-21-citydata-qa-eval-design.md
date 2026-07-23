# citydata QA eval 설계 — 시계열-근거 · metric-답변 · 팀 커버리지

> 상태: 설계 확정 대기(사용자 검토). 승인 후 구현 계획(별도 plan 문서)으로 분해.
> 소유: citydata 도메인(멘티). 팀원 도메인은 **읽기만** — 코드 수정 없음.

## 1. 목표 (Goal)

"AI 챗봇(3단계)" 준비를 위해, **실제 사용자 질문**에 대해 우리 데이터가
**정직하게 몇 %를 답하는지** 측정하는 평가셋을 만든다. 동시에 이 평가셋이
**"현행 골드셋에서 무엇을 D1에 채택할지"** 결정 도구가 되게 한다.

핵심 안티패턴 회피: 우리가 골드를 보고 질문을 짓고 우리가 정답/오답을 정하면
자문자답(주작)이다. → 질문 수요를 외부 실측에서, 답변을 정의된 metric에서만.

## 2. 두 설계 원칙 (사용자 지시)

### 원칙 1 — 질문 필터: "적재했기에 답하는 것만"

판별 기준 하나:

> **"서울 실시간도시데이터 API를 지금 한 번 호출해서 답 되나?"**
> → YES면 **제외**, "과거 누적이 있어야 답"이면 **포함**.

- ❌ 제외: "지금 강남 붐벼?", "지금 충전 되는 데?" — 서울 API가 실시간으로
  이미 답한다. 재서빙은 우리 가치가 아니다. (순수 현재 스냅샷: `place_latest`,
  `place_scorecard`, `charger_availability`)
- ✅ 포함: "무슨 요일 몇 시가 한산해?", "지금 평소보다 붐벼?", "요즘 뜨는 상권?",
  "20대는 언제 몰려?" — **시계열을 쌓아야만** 답 가능. 서울 API는 과거를 안 준다.

주의: `ppltn_anomaly`·`ppltn_trend`·`hot_commerce`는 grain이 "장소당 현재 1행"
이어도 **baseline/변화율이 과거 누적에서 나오므로 포함**이다. grain이 아니라
"답에 과거가 필요한가"로 가른다.

### 원칙 2 — 답변 표면: "정의된 metric을 통해서만"

- 챗봇은 **정의된 metric으로만** 답한다. 자유 SQL 금지.
- 이 스택은 dbt-Trino라 MetricFlow **쿼리 실행**은 안 되지만, dbt-core가
  `semantic_models:`/`metrics:` yml을 **매니페스트에 파싱**한다 → 이것이 정의된
  시맨틱 레이어. (나중에 SL 어댑터를 붙이면 그대로 쿼리 가능.)
- QA seed는 raw 테이블/컬럼이 아니라 **metric 이름**으로 라우팅한다.

## 3. 범위 결정 — 정의(쓰기)와 커버리지(읽기)의 분리

사용자 딜레마: 내 것만 하면 "이미 팀원이 만든 걸 중복 생산"할 위험, 팀 전체를
건드리면 충돌·혼란. → **가짜 딜레마.** 읽기와 쓰기를 분리해 해소한다.

| | 내 도메인(citydata) | 팀원 도메인 |
|---|---|---|
| **metric 정의(쓰기)** | ✅ 내가 정의 | ❌ 안 건드림 |
| **커버리지 참조(읽기)** | ✅ | ✅ **읽기만** (`information_schema`) |

근거·선례: `gold_culture_qa_eval.sql`(성진님)이 이미 `information_schema`로
citydata/weather/transit 스키마를 **읽기만** 하고 아무것도 바꾸지 않는다(17~22줄).
검증된 안전 패턴을 그대로 따른다.

## 4. 채택 결정 매트릭스 (이 설계의 최종 산출 의미)

각 실수요 질문을 eval이 3가지로 분류한다:

- 🟢 **내 citydata metric이 답함** → **D1에 채택**
- 🔵 **팀원 기존 골드가 이미 답함** (예: "잠실 날씨" → weather 골드) →
  **citydata에 만들지 말 것(중복 방지)** → 팀원 것 사용 또는 화요일 회의 조율
- 🔴 **아무도 못 답함** (예: 맛집 인기/추천) → **진짜 팀 갭 → 로드맵/신규 소스**

이 매트릭스가 "골드셋에서 무엇을 채택할지"의 근거가 된다.

## 5. 질문 수요 소싱 (외부 실측)

- 소스: 네이버 데이터랩 검색어트렌드 + 자동완성 (`mine_search_demand.py`,
  산출 `ranked_search_demand.json`).
- 방법: 자동완성으로 후보를 네이버가 확장(실제 검색 패턴) → 데이터랩 앵커정규화로
  상대 수요 랭킹.
- 실측 결과(2026-07-21, 최근 90일): 서울 장소 검색 수요 = 일반장소 30.6% /
  맛집 24.0% / 특정시설 17.6% / 날씨 15.5% / 교통·역 6.0% / 축제 2.7% /
  실시간혼잡 1.3% / 주차 0.3%.
- 질문 30문항은 이 **수요 비율에 맞춰** 배분한다(수요가 큰 축에 더 많이). 단
  원칙 1 필터를 통과한 것만(실시간 스냅샷 질문 제외).

## 6. 산출물 (3개, 전부 citydata 도메인 내)

### 6.1 `models/semantic/_citydata_metrics.yml` — 시맨틱 레이어

dbt 네이티브 `semantic_models` + `metrics`. 시계열 골드 위에 정의.
초기 metric 후보(원칙 1 통과분):

| metric | 소스 mart | 답하는 질문 | measure/dim |
|---|---|---|---|
| `congestion_by_dow_hour` | `gold_citydata_ppltn_by_time` | 무슨 요일 몇 시가 한산해? | avg(congest) × area×dow×hour |
| `population_peak_daily` | `gold_citydata_ppltn_daily` | 이 장소 하루 최대 인구? | max(ppltn) × area×date |
| `congestion_hourly_profile` | `gold_citydata_ppltn_hourly` | 이 장소 몇 시가 붐벼? | avg(congest) × area×hour |
| `congestion_anomaly` | `gold_citydata_ppltn_anomaly` | 지금 평소보다 붐벼? | z_score × area |
| `commerce_momentum` | `gold_citydata_hot_commerce` | 요즘 뜨는 상권? | growth × area |
| `visitor_segment_pattern` | `gold_citydata_ppltn_demographics` | 20대는 언제 몰려? | age/sex ratio × area×dow×hour |
| `spend_daily_trend` | `gold_citydata_cmrcl_daily` | 이 동네 소비 추이? | sum(pay) × area×date |
| `weather_congestion_pattern` | `gold_citydata_ppltn_x_weather_hourly` | 비 올 때 덜 붐벼? | congest×precip × dong×hour |
| `congestion_forecast` | `gold_citydata_ppltn_forecast` | 이번 주말 몇 시가 한산? | expected × area×weekend×hour |

(구현 시 measure/dimension/entity 구체화. 각 metric은 원칙 1을 만족 = 시계열 필요.)

### 6.2 `seeds/seed_citydata_qa_questions.csv` — 질문 카탈로그

컬럼(안):

```
question_id, persona_uuid, persona_summary, home_region, visit_context,
persona_lens, question_text,
demand_cluster,           # 6절 수요 클러스터(맛집/날씨/…) — 수요 근거 추적
requires_timeseries,      # 원칙 1 통과 여부(항상 true; false면 애초 제외)
target_metric,            # 🟢 citydata metric 이름(정의된 것) 또는 공백
covered_by_domain,        # 🟢citydata / 🔵weather·transit·culture·commerce / 🔴none
covered_by_relation,      # 실제 커버 골드 schema.table (읽기 검증 대상) 또는 공백
adoption,                 # adopt / duplicate_skip / gap (파생·문서용, eval이 재계산)
unanswerable_reason       # 🔴일 때 왜 못 답하나 + 필요한 신규 소스
```

- 페르소나: `2026-07-21-citydata-qa-personas-snapshot.json`(30명, 랜덤 샘플).
- 질문은 수요 소싱 기반, 원칙 1 필터 통과분만.

### 6.3 `models/gold/gold_citydata_qa_eval.sql` — 거버넌스 eval

`gold_culture_qa_eval.sql` 패턴을 그대로. 검사:

1. **metric_defined** — `target_metric`이 정의된 citydata metric인가.
   dbt `graph.metrics`로 정의된 metric 이름 집합을 Jinja가 주입(매니페스트 실측).
   metric이 yml에서 삭제되면 자동 불일치 → drift 노출.
2. **relation_exists** — `covered_by_relation`이 실존하는가.
   `information_schema.tables`를 팀 스키마(citydata + weather + transit + culture +
   commerce) 범위로 **읽기**. 골드가 drop/rename되면 자동 노출.
3. **coverage_status** — 위 둘로 🟢/🔵/🔴 재계산(seed의 adoption과 대조 = 드리프트).
4. **eval_ready** — 🟢이고 metric_defined이고 relation_exists.

소비 지표:
- `count_if(coverage='🟢adopt') / count(*)` = citydata 자체 커버리지
- `count_if(coverage='🔵teammate') / count(*)` = 팀원이 이미 커버(중복 방지 대상)
- `count_if(coverage='🔴gap') / count(*)` = 진짜 갭(로드맵)
- `meta.external = false` (내부 전용).

## 7. Non-Goals (명시)

- 팀원 도메인(weather/transit/culture/commerce) 코드 **수정 금지**. 읽기만.
- 새 metric mart를 무분별하게 만들지 않음 — 🔵(팀원 커버)로 판명되면 안 만든다.
- 실시간 스냅샷 질문(place_latest 류) 평가 대상 아님(원칙 1).
- 맛집 인기/리뷰 등 🔴 갭을 이 작업에서 해결하지 않음(신규 소스 = 별도 결정).

## 8. 열린 질문 / 캐비앳

- `graph.metrics` 주입 타이밍: dbt compile/run 단계에서 populate. eval 모델에서
  Jinja로 metric 이름 VALUES 리스트를 emit하는 방식 검증 필요(빌드 시). 실패 시
  대안 = 얇은 `_citydata_metric_registry` seed로 metric→mart 미러링.
- 검색어 ≠ 챗봇 질문: 데이터랩은 수요 프록시일 뿐, 문장형 질문과 정확히 같지
  않음. 수요 배분 근거로만 쓰고 문구는 페르소나가 자연어화.
- 🔵 판정의 정확도: 팀원 골드가 "정말 그 질문을 답하는지"는 description 기반
  추정. 화요일 회의에서 소유·정합 확인 필요(특히 cross 중복 이슈와 연계).
- 수요 시간창: 90일·월 단위 사용. 실시간성 질문 비중 재고 시 30일·일 단위 재수집.

## 9. 참고

- 팀 metric-mart 컨벤션: `dbt/domains/culture/docs/design/2026-07-20-culture-qa-metric-marts.md`
- eval 선례: `dbt/domains/culture/models/gold/gold_culture_qa_eval.sql`
- 수요 산출: `mine_search_demand.py` → `ranked_search_demand.json`
- 페르소나: `2026-07-21-citydata-qa-personas-snapshot.json`
