# usage_patterns 표기 규약 (정본) — id·파라미터·예시값·조합·검증·보안 감사

commerce 가 `meta.serving.usage_patterns` 로 선언·게시하는 질의 패턴의 작성 규약이다.
ASAC-DBT#471(Serving#178·#179 후속)로 정본화했다. **선언이 곧 게시 결과**이므로
(export → `d1_usage_patterns` → 게이트웨이 `run_pattern` 실행), 이 규약 위반은 곧
소비자 장애다. 근거는 게이트웨이 실측(ASK-Seoul-Serving `marketplace/src/index.js`
`handleRunPattern`, 2026-08-08 확인)이며, 게이트웨이 계약이 바뀌면 이 문서를 같이 고친다.

## 0. 게이트웨이 실행 계약 (실측 요약 — 규약의 전제)

| # | 계약 | 위반 시 |
|---|---|---|
| 1 | `product_id`·`pattern_id` 는 `^[a-z0-9_]+$` | 400 invalid id |
| 2 | 실행 전 `--`·`/* */` 주석 제거 후 `SELECT`/`WITH` 단일문만 | 400 pattern not runnable |
| 3 | `:name` 자리는 등장 순서대로 `?` prepared bind (값 주입 불가) | — |
| 4 | **모든 파라미터 필수**(기본값 없음), 문자열/숫자만, 선언 밖 파라미터 400 | 400 missing/unknown parameter |
| 5 | 이름이 `n`/`limit`/`top_n` 인 파라미터만 숫자 강제 + 상한 5000 clamp | 다른 이름은 상한 미적용 |
| 6 | 결과 행수 5000 절단, `verified_at` 없으면 실행 거부(runnable=false) | 409 pattern not verified |
| 7 | **테이블 스코프 미검사** — 저장 SQL 은 공유 D1 전체에 실행됨 | (commerce 측 감사로 차단, §6) |

## 1. pattern_id

- `^[a-z0-9_]{1,64}$`. **하이픈 금지**(Serving#178 — 77건이 400 으로 죽었던 원인).
- 같은 d1_table 안에서 유일. 교차 테이블 패턴(§5)은 `x_` 접두사 예약.
- 이름은 질문의 축을 담는다: `<축>_<관점>_<형태>` 권장 (`gu_churn_rank_topn`,
  `category_seoul_timeseries`). 개명은 소비자 파손이므로 게시 후엔 사실상 불가 — 처음에 맞게.

## 2. 파라미터 — 실바인딩만

- 가변 축은 반드시 `col = :name` 실바인딩. **`값 /* :name */` 형(값 박힘 + 주석 표식) 금지**
  (Serving#179 — 200 을 반환하면서 항상 같은 답을 주는 조용한 오답의 원인).
- 행수 제한은 `LIMIT :n`(또는 `:limit`/`:top_n`) — 이 세 이름만 게이트웨이가 상한(5000)을
  누른다. `LIMIT :rows` 처럼 다른 이름을 쓰면 상한이 안 걸린다(감사기가 반려).
- 모든 파라미터는 소비자가 값을 줘야 실행된다(계약 4). "생략하면 전체" 의미가 필요하면
  센티널을 쓴다(§4). 선택 파라미터·기본값은 게이트웨이 계약에 없다(역제안 진행 중 — §7).
- 같은 값을 여러 자리에 쓰려면 같은 `:name` 을 반복한다(서브쿼리 포함 — `gu_regime_diagnosis`
  의 `:y` 3회가 예).

## 3. 예시값 주석

- SQL 첫 줄에 한 줄: `-- :y='2025', :gu_code='11680', :n=10`.
  문자열 축은 `'값'`, 숫자는 그대로. 부가 설명은 값 뒤 괄호(`-- :gu_code='11680' (강남구)`).
- 이 주석은 (a) 검증 스크립트의 예시값 관용 추출, (b) 플레이그라운드 입력칸 힌트,
  (c) 사람 리뷰의 근거다. **예시값 조합은 실행 시 0행 초과**여야 한다(0행 예시는 예시가 아니다).
- 예시값은 실데이터에서 고른다 — 코드값(gu_code·category 등)을 지어내지 않는다.

## 4. 조합 관용구 — 식별자 바인딩 없이 구조를 고르는 법

게이트웨이는 값만 bind 하고 식별자(컬럼/방향/테이블)는 bind 못 한다(계약 3). 그래도 아래
관용구로 **하나의 패턴이 여러 고정 패턴을 대체**할 수 있다. 전부 값 바인딩만 쓰므로 인젝션
여지가 없고(§6), 실측 검증을 통과했다.

| 관용구 | 골격 | 질문 표기 의무 |
|---|---|---|
| 차원 스위치 | `CASE :dim WHEN 'gu' THEN gu_code ELSE category END` — GROUP BY 에 같은 식 반복 | `:dim ∈ {gu, category}` 명시 |
| 정렬 방향 스위치 | `ORDER BY CASE WHEN :dir='asc' THEN m END ASC, CASE WHEN :dir='desc' THEN m END DESC` | `:dir ∈ {asc, desc}` 명시 |
| 센티널(전체) | `AND (:gu_code = 'ALL' OR gu_code = :gu_code)` | `'ALL' = 전체` 명시 |
| 임계값 | `HAVING SUM(stock_start) >= :min_stock` | 권장 기본 예시값 명시 |
| 기간 창 | `WHERE y BETWEEN :from_y AND :to_y` | 축 범위(실데이터 min/max) 명시 |
| 지표 스위치 | `CASE :metric WHEN 'churn' THEN … ELSE … END` | 허용 값 목록 명시 |
| **배열 IN** | `WHERE gu_code IN (SELECT value FROM json_each(:gus))` | `:gus` 는 **JSON 배열 문자열** (`'["11680","11650"]'`) 임을 명시 |

- 스위치·센티널의 허용 값은 `question_ko` 나 `axes` 에 반드시 적는다 — 소비자(AI)는 선언만
  보고 값을 고른다.
- 미지원 스위치 값이 오면 결과가 0행이거나 ELSE 가지로 흐른다 — CASE 에 ELSE 를 명시해
  오입력의 동작을 정의해 둘 것.

## 5. 교차 테이블 패턴 (`x_` 접두)

- 같은 D1 안 **commerce 소유 d1_\* 간** JOIN 만 허용(계약 7 + §6 감사). 게이트웨이 내부 표·
  타 도메인 표 참조는 감사가 게시를 차단한다.
- 조인 키는 실제 공유 축만: `gu_code`·`category`·`major`·`y`·`ym`·`dong`. 값 형식이 같은지
  실측으로 확인(코드 vs 이름 불일치 조인 금지).
- host 제품은 질문의 주인공 쪽 테이블로 하고 `pattern_id` 는 `x_` 접두. `requires` 에 `join` 포함.
- **게시 시점 차이 주의**: 두 테이블의 publication 이 다른 시점일 수 있다.
  `verified_publication_id` 는 host 제품 기준이므로, 상대 테이블 재게시 후 결과가 달라질 수
  있다 — 재검증 주기(§8)에서 함께 재실행된다.

## 6. 보안 감사 — 게시 전 기계 게이트

패턴 SQL 은 게이트웨이가 **공유 D1 전체에 verbatim 실행**하며 테이블 스코프를 검사하지
않는다(계약 7). 값 인젝션은 bind 가 막지만, "어떤 테이블을 읽는 SQL 이 게시되는가"는
게시하는 쪽(commerce)의 책임이다. 그래서:

- **정본 감사기**: `dags .../include/gold/pattern_audit.py` —
  ① SELECT/WITH 단일문 ② 쓰기/DDL/PRAGMA/ATTACH 금지 토큰 ③ FROM/JOIN 절의 **모든** 테이블이
  **SERVING_SPEC 파생 allowlist(commerce d1_\* 22종) ∪ CTE 이름 ∪ {json_each}** 안인지
  ④ `LIMIT :name` 이름 규약. 테이블 추출은 **토크나이저 기반**이다(정규식 아님) — 콤마 조인
  (`FROM d1_ok, _keys`)의 두 번째 이후 테이블·파생 테이블 뒤 콤마·스키마 한정(`main._keys`)·
  pragma TVF 를 모두 열거한다. (정규식 "FROM 뒤 첫 식별자"는 이들을 놓쳐 `_keys` 유출이
  가능했음이 레드팀으로 확증돼 폐기 — self-test 에 그 페이로드 8종이 회귀 케이스로 있다.)
- **게시 게이트**: export `_handoff_rows` 가 게시 직전 전 패턴을 감사, 위반분은
  **게시 제외 + `serve.pattern_audit_reject` 경보**(§19.1 규격). 통과분 게시는 막지 않는다.
- **사전 검사(CI/로컬)**: `python scripts/audit_pattern_sql.py --yml <yml>` (위반 시 exit 1),
  감사기 자체 검증은 `--self-test`(적대 23종 — 내부 표 참조·콤마 조인 은닉·스택 쿼리·
  주석 은닉·pragma TVF 등). dbt 저장소 단독 CI 는 `scripts/lint_usage_patterns.py`(E1~E7).
- **전체 차단(kill switch)** — 사고 시 모든 패턴 실행을 끄는 법, 빠른 순서로:
  1. (게이트웨이, 즉시) d1_usage_patterns 의 `verified_at` 을 NULL 로 — runnable=false 가
     되어 전 패턴 409. 데이터 파괴 없음, 재검증 실행으로 복구.
  2. (commerce, 다음 export) yml 에서 `verified_at` 제거 후 export — 같은 효과를 게시
     경로로. 개별 패턴만 끌 때도 동일(그 패턴의 verified_* 만 제거).
  3. (제품 단위) `external: false` → 카탈로그·실행 4경로가 모두 닫힌다(#434 방식).

## 7. 표현력의 경계 — 여기서 안 되는 것

계약 4(전 파라미터 필수)·3(식별자 bind 불가)·단일문 제약으로 **선택 파라미터 기본값,
패턴 체이닝(한 패턴 결과를 다음 입력으로), 자유 프로젝션·동적 피벗**은 패턴으로 표현할 수
없다. 이 영역은 마켓플레이스 역제안으로 관리한다 — 목록·논거·보안 영향은
[usage-patterns-proposal.md](usage-patterns-proposal.md) 참조. **여기 없는 표현이 필요하면
패턴을 우회하지 말고(§6 감사를 피하는 꼼수 금지) 그 문서에 항목을 추가하라.**

반대로 **배열 IN(가변 개수 다중 선택)은 계약 변경 없이 된다** — `json_each` 관용구(§4)를
쓴다. 값은 여전히 단일 문자열 스칼라라 bind 를 그대로 통과하고, 감사기는 `json_each` 만
테이블값 함수로 허용한다(`pragma_*` 는 차단). 실 D1 검증 2026-08-08.

## 8. 검증 (verified_*)

- **손 백필 금지.** `verified_rows`/`verified_at`/`verified_publication_id` 는
  `scripts/verify_usage_patterns.py --apply` 실측만 쓴다(#638 §5-1).
- 신규 패턴은 `verified_rows: 0` 자리만 두고 선언 → `--apply --only <d1_table>/` 로 실측
  스탬프. `verified_at` 이 없으면 게이트웨이가 실행을 거부하므로(계약 6) **검증 전 패턴은
  자동으로 비활성**이다 — 이것이 미검증 게시의 안전망이다.
- 재검증 기준: **SQL 이 바뀌면 반드시**, id 개명만이면 불요(증거는 SQL 실행의 증거다).
  예시값 조합은 최소 2벌로 실행해 파라미터가 실제로 결과를 바꾸는지 본다(#179 재발 방지).
- `allow_empty: true` 는 "0행이 정상"인 패턴만(예: 이상 감지 스크린) — 예시값 조합까지
  0행이어도 되는 패턴은 그 사실을 question_ko 에 적는다.

## 9. "무엇을 주는가" — 선언하지 말고 SQL 에서 뽑는다

- **패턴 항목에 임의 필드를 더하지 않는다.** 허용 필드는 org 공통 Serving Contract 가
  화이트리스트로 고정한다(`serving_contract/schema.yml` `usage_pattern_fields`):
  필수 `pattern_id`·`sql`, 선택 `question_ko`·`axes`·`requires`·`verified_rows`·
  `verified_at`·`verified_publication_id`·`allow_empty`·`insight_sample_ko`·`d1_table`.
  그 밖의 이름은 `serving-contract-gate` CI 가 `usage_pattern_unknown_field` 로 막는다.
  (`provides_ko` 같은 설명 필드를 두려다 이 게이트에 걸린 전례가 있다 — 게다가
  `d1_catalog_*` 핸드오프 스키마에 없는 필드는 **게시되지 않아** 소비자에게 닿지도 않는다.
  필드가 정말 필요하면 계약 확장을 #478 에 먼저 제안한다.)
- 그래서 "이 패턴이 무엇을 주는가"의 정본은 **SQL 자체**다. 카탈로그 생성기가 최종 SELECT 의
  프로젝션에서 **반환 컬럼**을 뽑아 표에 싣는다 — 손 선언이 아니라 실물 기준이라 SQL 과
  어긋날 수 없다. 질문(`question_ko`)·축(`axes`)·파라미터와 함께 읽으면
  "무엇을 묻고 / 무엇을 받고 / 어떤 축으로" 가 모두 드러난다.
- 사람용 카탈로그는 생성물이다: `python dags .../scripts/generate_pattern_catalog.py
  --yml <yml> --out docs/DB/gold/usage-patterns-catalog.md`. yml 을 고치면 재생성한다.
- 따라서 **반환 컬럼에 의미가 드러나는 별칭을 붙이는 것이 곧 문서화**다
  (`SUM(cnt) AS opened_total` 처럼 — `AS c1` 같은 이름은 카탈로그를 무의미하게 만든다).

## 10. 선언 블록 서식 (요약)

```yaml
- pattern_id: "category_seoul_timeseries"        # §1 슬러그
  question_ko: "특정 업종의 서울 전체 20년 추이는? (:category ∈ 실측 코드)"
  axes: "y(시계열) × 서울 합산 @ category 고정"
  verified_rows: 0                               # §8 — --apply 가 실측으로 갱신
  insight_sample_ko: "…실측 수치로…"
  sql: |
    -- :category='food'                          # §3 예시값 주석
    SELECT y, ... FROM d1_churn_yearly WHERE category = :category GROUP BY y ORDER BY y
  requires: [select_columns, sort, aggregate, group_by, filter_range]
```

geo 처럼 한 모델이 두 제품을 게시하면 `d1_table:` 을 패턴 레벨에 명시한다(라우팅).
