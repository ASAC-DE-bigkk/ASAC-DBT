# gold_culture_qa_eval — 페르소나 질문 카탈로그 + 라우팅 커버리지 (티어링 #20)

2026-07-20 · culture 도메인 · Q&A 트랙 2차 (로드맵 #269 후속, `2026-07-20-culture-qa-metric-marts.md` 다음 단계)

## 배경 / 왜

계획안(슬라이드 8·11)의 페르소나 Q&A 4단계 — ①가상 시민(Nemotron 한국 페르소나) → ②질문 생성 →
③라우팅·쿼리 → ④Pair 기록 — 중 **②③의 정적 뼈대**를 지금 dbt로 만든다. LLM 런타임이 필요한
답변×정답×faithfulness 페어(④)는 W7 에이전트 트랙 소관 — 이 마트가 그 트랙의 **입력(평가셋)**이 된다.

계획안 원칙 그대로:
- **"시계열을 적재했기에 답할 수 있는 질문만. 답은 정의된 metric을 통해서만"** (governed)
- **답 가능 → 평가셋** (커버리지%로 충실도 측정)
- **답 불가 → 로드맵** (미수집 도메인·장소 = 다음에 뭘 쌓을지의 재료)

## 페르소나 소싱 — Nemotron-Personas-Korea

- 소스: HuggingFace `nvidia/Nemotron-Personas-Korea` (**CC-BY-4.0** — seed 문서·yml description에 출처 표기).
  datasets-server API로 **인증 없이** 조회 가능(실측 확인). 필드가 계획안과 일치:
  age·sex·occupation·district(예: "광주-서구") + travel/culinary/family/sports/arts_persona.
- **샘플링 규칙(재현 가능)**: `rows?offset=0&length=100` 1회 호출 → 인덱스 0, 7, 14, …, 98 (7 간격)
  **15명** 고정 선택. 원본 JSON을 `docs/design/2026-07-20-qa-personas-snapshot.json`으로 저장(출처 스냅샷).
- **거주지 해법(계획안 그대로)**: 페르소나 거주지는 전국 → 각자에게 "서울 방문 상황"(visit_context)을
  부여. 예: 광주 74세 하역 종사원 → "아내와 서울 고궁·유적 나들이 상경".
- 외부 의존은 **seed 생성 시 1회뿐** — 이후 dbt 빌드는 완전 오프라인.

## 질문 생성 + 검수 게이트

- 페르소나 15명 × 각 2문항 = **~30개** 초안: 답가능 **~20**(현행 12개 gold로 라우팅 가능) +
  답불가 **~10**(로드맵 재료 — weather_fit·commerce 차단·미수집 영역을 의도적으로 포함).
- 렌즈: travel/culinary/family 중심(+sports/arts 소수). 질문은 페르소나 텍스트에 근거해 생성
  (예: 역사유적 선호 → "경복궁 근처 이번 주말 행사"), 라우팅 대상 마트·컬럼을 함께 큐레이션.
- **검수 게이트(KBO seed #90 선례)**: 초안 30개를 표로 제시 → 사용자 검수·수정 → seed 확정.

## 설계

### seed — `seed_culture_qa_questions` (~30행)

| 컬럼 | 타입 | 정의 |
|---|---|---|
| question_id | varchar | `QA001`… (PK) |
| persona_uuid | varchar | Nemotron uuid — 출처 추적(스냅샷 JSON과 조인 가능) |
| persona_summary | varchar | 한 줄 요약(예: "광주 서구 74세 하역 종사원, 아내와 역사유적 여행 선호") |
| home_region | varchar | 원본 district(예: 광주-서구) |
| visit_context | varchar | 부여된 서울 방문 상황 |
| persona_lens | varchar | travel/culinary/family/sports/arts |
| question_text | varchar | 자연어 질문 |
| target_mart | varchar(null 허용) | 라우팅 대상 gold 마트명(답가능 시 필수) |
| target_columns | varchar(null 허용) | 근거 컬럼(콤마 구분) |
| answerable | boolean | 현행 데이터로 답 가능 여부(큐레이션 의도) |
| unanswerable_reason | varchar(null 허용) | 답불가 사유 + 로드맵 힌트(답불가 시 필수) |

### gold — `gold_culture_qa_eval` (그레인 question_id, ~30행)

seed를 Trino `{{ target.database }}.information_schema.tables`(`table_schema = target.schema`)와
LEFT JOIN하여 라우팅 대상 마트의 **실존을 실측**:

| 추가 컬럼 | 타입 | 정의 |
|---|---|---|
| mart_exists | boolean | target_mart가 카탈로그에 실존하는가(측정값) |
| eval_ready | boolean | answerable AND mart_exists — W7 평가셋 투입 가능 |

- governed 포인트: answerable(큐레이션 의도) vs mart_exists(측정값) 분리 —
  마트가 rename/drop되면 **eval_ready가 자동으로 꺼져 드리프트가 드러남**(정적 문서와의 차별점).
- **contract enforced** + **`meta.external: false`**(내부 전용 — 대시보드 외부 카탈로그 자동 제외).
- 커버리지 소비 예(모델 주석에 기재): `count_if(eval_ready) / count_if(answerable)` = 라우팅 건전성,
  `count_if(answerable) / count(*)` = 질문 커버리지(계획안의 "커버리지%로 충실도 측정").

### 테스트

- generic: question_id `not_null` + `unique`
- singular `assert_qa_eval_invariants`:
  - answerable=true → target_mart not null
  - answerable=false → unanswerable_reason not null
  - 그레인 유일
- singular(warn) `assert_qa_eval_routing_drift`: answerable=true인데 mart_exists=false인 행 —
  **severity warn**(빌드는 통과, 라우팅 드리프트 신호만).

## 스코프 밖

- LLM 답변×정답×faithfulness 페어 생성·Trust Score 계산 — W7 에이전트 트랙(이 마트가 입력).
- Nemotron 대량 샘플링·자동 질문 생성 파이프라인 — 필요 시 W7에서 확장.
- 대시보드 변경 — meta.external=false로 자동 내부 분류(추가 작업 없음).
- 타 도메인 마트로의 라우팅(질문이 culture 밖을 가리키면 답불가+로드맵으로 분류).

## 구현·검증 방식

1. 페르소나 샘플링(API 1회) → 스냅샷 JSON 저장 → 질문 30개 초안 → **검수 게이트**
2. 이슈(org 템플릿) + 브랜치 `feat/culture-qa-eval` → seed CSV + seed yml + gold 모델 + contract yml + 테스트
3. ASAC-DBT push → sample/dbt detached checkout → 컨테이너 `dbt build --select seed_culture_qa_questions gold_culture_qa_eval <tests>` → AC 실측 → PR(base dev) → dev 복귀

## AC (수용 기준)

- seed ~30행 로드(답가능 ~20 / 답불가 ~10), 검수 게이트 통과분만 포함
- gold ~30행 · answerable 전행 `mart_exists=true`(현행 라우팅 대상 전부 실존) · drift warn 0
- 불변식·contract 전부 PASS (컨테이너 dev)
- CC-BY-4.0 출처 표기(seed yml description + 이 문서) + 페르소나 스냅샷 JSON 존재
- 커버리지 실측치(질문 커버리지 %, 라우팅 건전성 %) PR body 기재
