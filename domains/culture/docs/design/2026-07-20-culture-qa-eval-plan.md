# gold_culture_qa_eval 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 설계 문서(2026-07-20-culture-qa-eval.md)의 구현 — Nemotron 페르소나 샘플링 → 질문 seed(검수 게이트) → information_schema 조인 gold + 테스트 → PR.

**Architecture:** Task 1(샘플링·초안·검수)은 코드 밖 큐레이션 — **검수 게이트에서 반드시 정지**. Task 2~3이 dbt 구현·검증·PR. 외부 의존(HF API)은 Task 1의 1회 호출뿐.

**Tech Stack:** HF datasets-server API(인증 불요), dbt seed/model(Trino/Iceberg), 컨테이너 elt-infra-airflow-scheduler-1(마운트 = `sample/dbt`).

## Global Constraints

- 수정 범위: `ASAC-DBT/domains/culture/` 만. 커밋 푸터 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` · PR 푸터 `🤖 Generated with [Claude Code](https://claude.com/claude-code)` · base=dev · 셀프 머지 금지.
- 이슈는 org 템플릿([Task]) — `type: task` 라벨은 레포에 없으므로 라벨 없이 생성.
- 컨테이너 검증 = push → `sample/dbt` detached checkout → dbt build → **`git checkout dev` 복귀**.
- dbt: `MSYS_NO_PATHCONV=1 docker exec elt-infra-airflow-scheduler-1 bash -c "cd /opt/airflow/dbt/domains/culture && /home/airflow/dbt-venv/bin/dbt build --select <targets> --project-dir . --profiles-dir . --target dev"`
- **CC-BY-4.0 출처 표기**: seed yml description + 스냅샷 JSON 헤더에 `nvidia/Nemotron-Personas-Korea` 명시.
- API 키·시크릿 출력 금지 (HF API는 무인증 — 키 자체가 없음).

---

### Task 1: 페르소나 샘플링 + 질문 30개 초안 + 검수 게이트

**Files:**
- Create: `domains/culture/docs/design/2026-07-20-qa-personas-snapshot.json` (선택된 15명 원본 + 출처 헤더)
- 중간산출(scratchpad): 초안 30문항 표 — 검수 후 Task 2의 CSV 원료

**Interfaces:**
- Produces: 검수 통과된 질문 30개(question_id·persona_uuid·…·unanswerable_reason 11필드 값)

- [ ] **Step 1-1: 샘플링 (재현 규칙 고정)**

```bash
curl -s "https://datasets-server.huggingface.co/rows?dataset=nvidia%2FNemotron-Personas-Korea&config=default&split=train&offset=0&length=100" -o <scratchpad>/nemotron-100.json
```

python으로 인덱스 `0,7,14,…,98`(7 간격, 15명) 선택 → `2026-07-20-qa-personas-snapshot.json` 저장:

```json
{
  "source": "nvidia/Nemotron-Personas-Korea (HuggingFace, CC-BY-4.0)",
  "sampling": "datasets-server rows offset=0 length=100, indices 0..98 step 7 (15 personas), sampled 2026-07-20",
  "personas": [ ...15개 원본 row 그대로... ]
}
```

- [ ] **Step 1-2: 질문 초안 30개 생성** — 페르소나별 2문항. 각 문항에 11필드 전부 채움:
  - 답가능 ~20: target_mart는 **현행 12개 gold 중에서만**, target_columns는 해당 마트 실컬럼만
  - 답불가 ~10: weather_fit(예보)·commerce(상권)·미수집 영역 의도 포함, unanswerable_reason에 로드맵 힌트
  - visit_context: 페르소나 텍스트 근거로 "서울 방문 상황" 부여

- [ ] **Step 1-3: 검수 게이트 — 정지** 🛑

초안 30개를 표로 제시하고 사용자 검수 대기. 수정 반영 후에만 Task 2 진행.

---

### Task 2: seed + gold + contract + 테스트 구현

**Files:**
- Create: `domains/culture/seeds/seed_culture_qa_questions.csv` (검수 통과분)
- Modify: `domains/culture/seeds/schema.yml` (seed 블록 추가)
- Modify: `domains/culture/dbt_project.yml` (seeds column_types 추가)
- Create: `domains/culture/models/gold/gold_culture_qa_eval.sql`
- Modify: `domains/culture/models/gold/_culture_gold__models.yml` (끝에 블록 추가)
- Test: `domains/culture/tests/assert_qa_eval_invariants.sql`, `domains/culture/tests/assert_qa_eval_routing_drift.sql`

**Interfaces:**
- Consumes: Task 1 검수 통과 30문항, `{{ target.database }}.information_schema.tables`
- Produces: `iceberg_dev.culture.gold_culture_qa_eval` (그레인 question_id, ~30행, mart_exists·eval_ready 포함)

- [ ] **Step 2-1: 이슈 + 브랜치**

이슈 제목 `[Task] gold_culture_qa_eval — 페르소나 질문 카탈로그 + 라우팅 커버리지`. body: 설계 문서 링크 + Nemotron 샘플링 규칙 + AC. 브랜치 `feat/culture-qa-eval` (dev 최신에서).

- [ ] **Step 2-2: seed CSV 작성** — 헤더:

```csv
question_id,persona_uuid,persona_summary,home_region,visit_context,persona_lens,question_text,target_mart,target_columns,answerable,unanswerable_reason
```

값 규칙: answerable은 `true`/`false` 소문자. null 필드는 빈 값. 텍스트에 콤마 포함 시 큰따옴표 감싸기.

- [ ] **Step 2-3: `dbt_project.yml` seeds 블록에 추가**

```yaml
    seed_culture_qa_questions:
      +column_types: {answerable: boolean}
```

- [ ] **Step 2-4: `seeds/schema.yml` 끝에 seed 블록**

```yaml
  - name: seed_culture_qa_questions
    description: 페르소나 질문 카탈로그(티어링 #20, 설계 2026-07-20-culture-qa-eval.md). 페르소나 원천 = nvidia/Nemotron-Personas-Korea (HuggingFace, CC-BY-4.0) — 15명 샘플(스냅샷 docs/design/2026-07-20-qa-personas-snapshot.json), 질문은 페르소나 텍스트 근거 큐레이션(검수 게이트 통과분). 답가능=W7 평가셋 입력, 답불가=수집 로드맵 재료.
    columns:
      - name: question_id
        description: 질문 ID (QA001…)
        tests: [not_null, unique]
      - name: persona_uuid
        description: Nemotron 페르소나 uuid — 스냅샷 JSON과 조인 가능
        tests: [not_null]
      - name: question_text
        description: 자연어 질문
        tests: [not_null]
      - name: persona_lens
        description: 질문을 만든 페르소나 렌즈
        tests:
          - not_null
          - accepted_values:
              values: ["travel", "culinary", "family", "sports", "arts"]
      - name: answerable
        description: 현행 culture gold로 답 가능 여부(큐레이션 의도 — 실측은 gold의 mart_exists)
        tests: [not_null]
```

- [ ] **Step 2-5: gold 모델** — `models/gold/gold_culture_qa_eval.sql`:

```sql
-- gold(Q&A 거버넌스): 페르소나 질문 카탈로그 × 라우팅 실측(티어링 #20). 그레인 question_id.
-- 계획안 "답 가능 → 평가셋(커버리지%), 답 불가 → 로드맵"의 데이터 구현 — W7 에이전트 트랙의 입력.
-- answerable(큐레이션 의도) vs mart_exists(information_schema 실측) 분리 —
--   라우팅 대상 마트가 rename/drop 되면 eval_ready가 자동으로 꺼져 드리프트가 드러난다(governed).
-- 커버리지 소비 예: count_if(eval_ready)/count_if(answerable)=라우팅 건전성,
--   count_if(answerable)/count(*)=질문 커버리지. meta.external=false(내부 전용).

with q as (
    select * from {{ ref('seed_culture_qa_questions') }}
),

-- 현행 카탈로그의 실존 테이블(스키마 = 이 타깃의 culture 스키마)
marts as (
    select table_name
    from {{ target.database }}.information_schema.tables
    where table_schema = '{{ target.schema }}'
),

joined as (
    select
        q.question_id,
        q.persona_uuid,
        q.persona_summary,
        q.home_region,
        q.visit_context,
        q.persona_lens,
        q.question_text,
        q.target_mart,
        q.target_columns,
        q.answerable,
        q.unanswerable_reason,
        (m.table_name is not null)                  as mart_exists,
        (q.answerable and m.table_name is not null) as eval_ready
    from q
    left join marts m on m.table_name = q.target_mart
)

select * from joined
```

- [ ] **Step 2-6: `_culture_gold__models.yml` 끝에 계약 블록**

```yaml
  - name: gold_culture_qa_eval
    description: 페르소나 질문 카탈로그 × 라우팅 커버리지(티어링 #20, 그레인 question_id). 페르소나 원천 nvidia/Nemotron-Personas-Korea(CC-BY-4.0) 15명 샘플. answerable(큐레이션)과 mart_exists(information_schema 실측) 분리 — eval_ready=W7 평가셋 투입 가능. 답불가 행의 unanswerable_reason=수집 로드맵 재료. 내부 전용(meta.external=false).
    config:
      contract:
        enforced: true   # published gold 계약(#180)
      meta:
        external: false  # Q&A 거버넌스 내부 마트 — 외부 카탈로그 노출 제외(#269)
    columns:
      - name: question_id
        description: 질문 ID(QA001…) — PK
        data_type: varchar
        tests: [not_null, unique]
      - name: persona_uuid
        description: Nemotron 페르소나 uuid(출처 추적 — 스냅샷 JSON 조인 키)
        data_type: varchar
      - name: persona_summary
        description: 페르소나 한 줄 요약
        data_type: varchar
      - name: home_region
        description: 페르소나 원거주지(Nemotron district)
        data_type: varchar
      - name: visit_context
        description: 부여된 서울 방문 상황(계획안 거주지 해법)
        data_type: varchar
      - name: persona_lens
        description: 질문 생성 렌즈(travel/culinary/family/sports/arts)
        data_type: varchar
      - name: question_text
        description: 자연어 질문
        data_type: varchar
      - name: target_mart
        description: 라우팅 대상 gold 마트명(답가능 시 필수, 답불가면 null)
        data_type: varchar
      - name: target_columns
        description: 근거 컬럼(콤마 구분)
        data_type: varchar
      - name: answerable
        description: 현행 데이터로 답 가능 여부(큐레이션 의도)
        data_type: boolean
        tests: [not_null]
      - name: unanswerable_reason
        description: 답불가 사유 + 로드맵 힌트(답불가 시 필수)
        data_type: varchar
      - name: mart_exists
        description: target_mart가 카탈로그에 실존하는가 — information_schema 실측
        data_type: boolean
      - name: eval_ready
        description: answerable AND mart_exists — W7 평가셋 투입 가능(라우팅 건전성 신호)
        data_type: boolean
```

- [ ] **Step 2-7: 테스트 2종**

`tests/assert_qa_eval_invariants.sql`:

```sql
-- qa_eval 불변식: 그레인 유일 + 답가능→target_mart 필수 + 답불가→unanswerable_reason 필수.
with dupes as (
    select question_id, count(*) as n
    from {{ ref('gold_culture_qa_eval') }}
    group by question_id
    having count(*) > 1
),
bad as (
    select question_id
    from {{ ref('gold_culture_qa_eval') }}
    where (answerable and target_mart is null)
       or ((not answerable) and unanswerable_reason is null)
)
select question_id, 'dupe' as violation from dupes
union all
select question_id, 'invariant' as violation from bad
```

`tests/assert_qa_eval_routing_drift.sql`:

```sql
-- 라우팅 드리프트 신호(warn): 답가능으로 큐레이션했는데 대상 마트가 카탈로그에 없음.
-- 마트 rename/drop 시 여기서 드러난다 — 빌드는 통과(warn), 질문 재큐레이션 트리거.
{{ config(severity='warn') }}

select question_id, target_mart
from {{ ref('gold_culture_qa_eval') }}
where answerable and not mart_exists
```

---

### Task 3: 컨테이너 빌드 + AC 실측 + PR

- [ ] **Step 3-1: 커밋 + push** (커밋 메시지에 #이슈 참조 + Co-Authored-By 푸터)
- [ ] **Step 3-2: 컨테이너 빌드**

```bash
cd sample/dbt && git fetch origin && git checkout --detach origin/feat/culture-qa-eval
# 컨테이너에서:
dbt build --select seed_culture_qa_questions gold_culture_qa_eval assert_qa_eval_invariants assert_qa_eval_routing_drift --project-dir . --profiles-dir . --target dev
```

Expected: seed 1 + model 1 + generic(seed not_null·unique·accepted_values + gold not_null·unique) + singular 2 전부 PASS, drift는 WARN 0.

- [ ] **Step 3-3: AC 실측** (Trino):

```sql
select count(*) total,
       count_if(answerable) answerable_n,
       count_if(eval_ready) eval_ready_n,
       count_if(answerable and not mart_exists) drift_n
from iceberg_dev.culture.gold_culture_qa_eval
-- 기대: total~30, answerable~20, eval_ready = answerable_n (drift 0)
```

커버리지 계산: 질문 커버리지 = answerable_n/total, 라우팅 건전성 = eval_ready_n/answerable_n(=100%).

- [ ] **Step 3-4: PR 생성** — body에 커버리지 실측치·CC-BY-4.0 표기·검수 게이트 통과 명시. sample/dbt `git checkout dev` 복귀.

---

### Task 4: 마무리

- [ ] **Step 4-1**: 로드맵 #269 코멘트 — qa_eval 완료 + 커버리지 실측치 + "티어링 착수가능분 완료" 상태.
- [ ] **Step 4-2**: 티어링 TSV #20 구축상태 갱신.
- [ ] **Step 4-3**: 메모리 갱신(culture-qa-metric-marts에 qa_eval 완결 추가).

## Self-review 체크 결과

- 스펙 커버리지: 설계 §소싱→T1, §seed/gold/테스트→T2, §구현·검증→T3, AC 전항목 T3-3에 매핑 ✓
- 플레이스홀더 없음 — CSV 헤더·SQL·yml 전부 실코드 ✓
- 타입 일관성: seed answerable boolean(+column_types) = gold 계약 boolean, mart_exists/eval_ready boolean 표현식 ✓
- 검수 게이트가 Task 1 안에 정지점으로 명시 ✓ (초안이 사용자 승인 없이 seed가 되는 경로 없음)
