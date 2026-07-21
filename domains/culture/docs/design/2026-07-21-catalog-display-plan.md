# 외부 카탈로그 전시 문구(display 계층) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** culture 외부 공개 gold 7종의 카탈로그 카드를 내부 개발 문맥 없이 외부 소비자가 읽고 바로 쓸 수 있는 상품 전시면으로 바꾼다.

**Architecture:** dbt `config.meta.display`(title·summary·caveat·use_cases)를 전시 문구의 소스 오브 트루스로 두고, 기존 `description`은 내부용으로 보존한다. `extract.py`가 manifest에서 display를 읽어 스냅샷에 옮기고, FastAPI 응답 모델과 카드/드로어가 이를 렌더한다. display가 없는 테이블은 필드 자체가 없어 기존 렌더로 폴백한다.

**Tech Stack:** dbt-trino(yml만 변경, SQL 무변경) · Python 3.11 + FastAPI/Pydantic · 정적 HTML/JS(빌드 도구 없음)

## Global Constraints

- 설계 문서 = `domains/culture/docs/design/2026-07-21-catalog-display-copy.md`. **전시 문구·컬럼 문구는 이 문서 §3·§4의 텍스트를 글자 그대로 옮긴다** — 임의 윤문 금지.
- 대상은 `meta.external: true` 인 culture gold **7종**뿐: `gold_culture_event_schedule` · `gold_culture_activity_by_dong` · `gold_culture_calendar_density` · `gold_culture_boxoffice_daily` · `gold_culture_booking_curve` · `gold_culture_event_crowd` · `gold_culture_dine_around`.
- 모델 `description`(내부용)의 **문구는 바꾸지 않는다**. 잘림 수정은 따옴표 씌우기 또는 이슈번호 제거만.
- SQL 모델 파일(`models/gold/*.sql`)은 이 작업에서 **한 줄도 건드리지 않는다**.
- dbt 실행은 컨테이너에서: `docker exec elt-infra-airflow-scheduler-1 /home/airflow/dbt-venv/bin/dbt ...`, Git Bash에서는 `MSYS_NO_PATHCONV=1` 접두 필수. 컨테이너는 `sample/dbt` 를 마운트하므로 브랜치 검증 후 **반드시 `git checkout dev` 로 복귀**.
- 한국어 출력이 깨지면 `PYTHONIOENCODING=utf-8` 을 붙인다.
- 커밋 메시지 마지막 줄: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- PR body 마지막 줄: `🤖 Generated with [Claude Code](https://claude.com/claude-code)`
- GitHub 이슈는 org `.github/ISSUE_TEMPLATE` 템플릿으로 생성한다.
- **내가 만든 PR은 셀프 머지하지 않는다** — 사용자가 명시적으로 지시할 때만.

## File Structure

| 파일 | 책임 | 태스크 |
|---|---|---|
| `ASAC-DBT/domains/culture/models/gold/_culture_gold__models.yml` | 전시 문구(display) + 컬럼 설명 + 잘림 수정 | T1·T2 |
| `ASAC-DBT/domains/culture/models/silver/_culture_silver__models.yml` | 잘림 1줄 수정 | T1 |
| `ASK-Seoul-Dashboard/extract.py` | manifest display → 스냅샷 4필드 | T3 |
| `ASK-Seoul-Dashboard/app/models.py` | 응답 계약에 4필드(Optional) | T3 |
| `ASK-Seoul-Dashboard/app/main.py` | `_summary()` 통과 | T3 |
| `ASK-Seoul-Dashboard/app/static/index.html` | 카드·리스트·드로어·검색 렌더 | T4 |

---

### Task 1: display 블록 7개 + 잘림 버그 수정 (ASAC-DBT)

**Files:**
- Modify: `domains/culture/models/gold/_culture_gold__models.yml`
- Modify: `domains/culture/models/silver/_culture_silver__models.yml`
- Reference: `domains/culture/docs/design/2026-07-21-catalog-display-copy.md` §3, §5

**Interfaces:**
- Produces: manifest 노드의 `config.meta.display.{title,summary,caveat,use_cases}` — T3의 `display_meta()` 가 이 경로를 읽는다. `use_cases` 는 문자열 리스트, 나머지는 문자열.

- [ ] **Step 1: 이슈 등록 + 브랜치**

org 템플릿 `feature_request.yml`(제목 접두 `[Feat] `, 라벨 `type: feature`)의 섹션 구조를 그대로 채운다.

```bash
cd ~/ask-seoul/ASAC-DBT && git checkout dev && git pull
gh issue create --repo ASAC-DE-bigkk/ASAC-DBT \
  --title "[Feat] culture 외부 gold 7종 카탈로그 전시 문구(display 계층) + description 잘림 수정" \
  --label "type: feature" \
  --body "$(cat <<'EOF'
### 배경 · 목적

외부 제공용 카탈로그 카드가 내부 개발 문맥을 그대로 노출한다(`#48`, `dim_admin_dong`, `scaffold`).
외부 소비자가 데이터셋을 이해하고 가져다 쓰기 어렵다.

추가로 YAML 비인용 스칼라에서 ` #` 이후가 주석 처리되어 **설명 15줄이 중간에서 잘려** manifest 에 실린다.
예) `gold_culture_booking_curve` → "…1공연 1행," 까지만 노출.

### 작업 내용 (체크리스트)

- [ ] 외부 공개 7종에 `config.meta.display`(title·summary·caveat·use_cases) 추가
- [ ] 외부 7종 컬럼 `description` 을 외부 소비자 언어로 정리(이슈번호·내부 모델명 제거)
- [ ] 잘림 15줄 수정 — 내부 마트는 문구 보존하고 따옴표만
- [ ] 설계·계획 문서 커밋

### 완료 조건 (Acceptance Criteria)

- [ ] dbt parse/compile 통과
- [ ] dbt test 통과
- [ ] 자기 도메인 스키마 밖에 쓰지 않음
- [ ] manifest 에서 `meta.external: true` 모델 7종 모두 display 4필드 보유
- [ ] culture yml 전체에서 ` #` 주석 잘림 0건
- [ ] SQL 모델 파일 무변경(문구 전용 PR)

도메인: 문화 (culture) / 레이어: gold
EOF
)"
git checkout -b feat/culture-catalog-display
```

- [ ] **Step 2: 잘림 검사 스크립트를 먼저 돌려 현재 상태(FAIL)를 기록**

```bash
cd ~/ask-seoul/ASAC-DBT/domains/culture
MSYS_NO_PATHCONV=1 PYTHONIOENCODING=utf-8 python -c "
import re, glob
bad = []
for f in glob.glob('models/**/*.yml', recursive=True):
    for i, l in enumerate(open(f, encoding='utf-8'), 1):
        m = re.match(r'\s*description:\s*(?![\"|>\x27])(.*)', l)
        if m and ' #' in m.group(1):
            bad.append(f'{f}:{i}')
print('truncated:', len(bad))
for b in bad: print(' ', b)
"
```

Expected: `truncated: 15`

- [ ] **Step 3: 외부 7종에 display 블록 추가**

각 모델의 `config:` 아래 `meta:` 에 `display:` 를 넣는다. `meta:` 가 없으면 만든다.
문구는 설계 §3 을 **글자 그대로** 옮긴다. 예(`gold_culture_dine_around`, 이미 `meta:` 존재):

```yaml
    config:
      contract:
        enforced: true   # published gold 계약(#180)
      meta:
        external: true   # 외부 카탈로그 공개(#269 티어링 v2 — 명시적 true 첫 사용, #308 AC)
        display:
          title: 문화·미식 동반 추천 지수
          summary: 동네마다 앞으로 90일간 예정된 문화행사량과 영업 중인 음식점 규모를 나란히 점수화했습니다. 두 값이 모두 높은 동네일수록 점수가 높아 "공연 보고 밥 먹기 좋은 동네" 정렬에 그대로 쓸 수 있습니다.
          caveat: 음식점 데이터가 연결된 동은 426곳 중 219곳입니다. 나머지 동은 문화 지표만 채워지고 점수는 비어 있습니다(has_dining_data 로 구분).
          use_cases:
            - 데이트·나들이 코스 추천
            - 상권 입지 검토
            - 지역 관광 코스 설계
```

`meta:` 가 없는 6종(`event_schedule`·`activity_by_dong`·`calendar_density`·`boxoffice_daily`·`booking_curve`·`event_crowd`)은 `contract:` 블록 다음에 새로 만든다:

```yaml
    config:
      contract:
        enforced: true   # published gold 계약(#180)
      meta:
        external: true   # 외부 카탈로그 공개(티어링 v2)
        display:
          title: 서울 문화행사 통합 일정
          summary: …(설계 §3-1 그대로)
          caveat: …
          use_cases:
            - …
```

주의 3가지:
1. `summary`·`caveat` 에 큰따옴표(`"`)가 들어가는 문구가 있다(§3-1, §3-7). YAML 비인용 스칼라에서 **문장 중간의 따옴표는 안전**하지만, 값이 `"` 로 **시작**하면 안 된다. 시작하는 경우 전체를 작은따옴표로 감싼다.
2. 어떤 값에도 ` #` 가 들어가면 안 된다 — 들어가면 그 지점부터 잘린다.
3. `calendar_density` 는 `caveat` 없음 — 키 자체를 넣지 않는다.

- [ ] **Step 4: 잘림 15줄 수정**

Step 2가 출력한 15줄 중, Step 3에서 이슈번호가 사라진 줄을 뺀 나머지를 처리한다.
- 외부 7종의 컬럼: 이슈번호 제거(T2에서 문구를 다시 손보므로 여기서는 `#48` 등 표기만 제거)
- 내부 마트(`slo_daily`·`qa_eval`·`venue_profile`·`sports_schedule`·`location_daily`)와 silver 1줄: **문구를 바꾸지 말고** 설명 전체를 큰따옴표로 감싼다.

```yaml
# before
    description: 시설(facility_id) 1행 프로필 — "그 공연장 어떤 곳이야"(Q&A metric, #278). …
# after — 내부 문구 보존, 따옴표만
    description: '시설(facility_id) 1행 프로필 — "그 공연장 어떤 곳이야"(Q&A metric, #278). …'
```

값 안에 큰따옴표가 있으므로 **작은따옴표로 감싼다**. 값 안에 작은따옴표가 있으면 큰따옴표로 감싼다. 둘 다 있으면 작은따옴표로 감싸고 내부 작은따옴표를 `''` 로 이스케이프한다.

- [ ] **Step 5: 잘림 검사 재실행 — 0건 확인**

Step 2와 같은 명령. Expected: `truncated: 0`

- [ ] **Step 6: dbt parse 후 manifest에서 display 실측**

```bash
cd ~/ask-seoul/sample/dbt && git fetch origin && git checkout --detach origin/feat/culture-catalog-display
cd ~/ask-seoul && MSYS_NO_PATHCONV=1 docker exec elt-infra-airflow-scheduler-1 \
  bash -lc "cd /opt/airflow/dbt/domains/culture && /home/airflow/dbt-venv/bin/dbt parse --project-dir . --profiles-dir . --target dev"
```

Expected: `Wrote manifest` 류 메시지, 에러 0

```bash
MSYS_NO_PATHCONV=1 docker exec elt-infra-airflow-scheduler-1 \
  bash -lc "cd /opt/airflow/dbt/domains/culture && python3 -c \"
import json
m = json.load(open('target/manifest.json'))
ext = {n['name']: n['config'].get('meta', {}).get('display')
       for n in m['nodes'].values()
       if n.get('resource_type') == 'model' and n['config'].get('meta', {}).get('external') is True}
print('external models:', len(ext))
for k, v in sorted(ext.items()):
    ok = bool(v) and all(v.get(f) for f in ('title', 'summary', 'use_cases'))
    print(('OK ' if ok else 'NG '), k, (v or {}).get('title'))
bad = [n['name'] for n in m['nodes'].values()
       if n.get('resource_type') == 'model' and n['name'].startswith('gold_')
       and (n.get('description','').rstrip().endswith((',', '(')) )]
print('truncated-looking descriptions:', bad)
\""
```

Expected: `external models: 7`, 7줄 모두 `OK`, `truncated-looking descriptions: []`

- [ ] **Step 7: dev 복귀 + 커밋**

```bash
cd ~/ask-seoul/sample/dbt && git checkout dev
cd ~/ask-seoul/ASAC-DBT
git add domains/culture/models/gold/_culture_gold__models.yml domains/culture/models/silver/_culture_silver__models.yml
git commit -m "$(cat <<'EOF'
feat(culture): 외부 gold 7종 display 전시 문구 + description 잘림 수정

- config.meta.display(title/summary/caveat/use_cases) 7종 추가
- YAML 비인용 스칼라의 ' #' 주석 잘림 15줄 수정(내부 문구는 따옴표만)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: 컬럼 설명 정리 + PR (ASAC-DBT)

**Files:**
- Modify: `domains/culture/models/gold/_culture_gold__models.yml`
- Reference: `domains/culture/docs/design/2026-07-21-catalog-display-copy.md` §4

**Interfaces:**
- Consumes: Task 1의 브랜치 `feat/culture-catalog-display`
- Produces: 외부 7종 컬럼 `description` — T4 드로어 스키마 탭이 그대로 렌더한다.

- [ ] **Step 1: 설계 §4의 표대로 컬럼 설명 교체**

외부 7종만. §4에 나열된 컬럼만 바꾸고 나머지는 손대지 않는다. 예:

```yaml
# gold_culture_activity_by_dong
      - name: admin_dong_code
        description: 행정동 코드 — 행정안전부 표준 10자리. 다른 행정동 데이터와 붙이는 조인 키
# gold_culture_event_schedule
      - name: quality_status
        description: 위치 정밀도 — dong_precise(행정동까지 확정) / gu_only(자치구까지) / unmatched(미확정)
```

- [ ] **Step 2: 내부 표기 잔존 검사**

```bash
cd ~/ask-seoul/ASAC-DBT/domains/culture
MSYS_NO_PATHCONV=1 PYTHONIOENCODING=utf-8 python -c "
import re
EXT = ['gold_culture_event_schedule','gold_culture_activity_by_dong','gold_culture_calendar_density',
       'gold_culture_boxoffice_daily','gold_culture_booking_curve','gold_culture_event_crowd',
       'gold_culture_dine_around']
BAN = ['#', 'dim_admin_dong', 'int_culture_', 'silver_culture_', 'citydata gold', 'scaffold', '스카폴드', 'percent_rank', 'Trino']
src = open('models/gold/_culture_gold__models.yml', encoding='utf-8').read()
blocks = re.split(r'\n  - name: ', src)
hits = 0
for b in blocks:
    nm = b.split('\n')[0].strip()
    if nm not in EXT: continue
    for i, l in enumerate(b.split('\n')):
        if not l.strip().startswith('description:'): continue
        if i == 0: continue
        for w in BAN:
            if w in l:
                hits += 1; print(f'{nm}: {w} :: {l.strip()[:80]}')
print('remaining internal markers in external columns:', hits)
"
```

Expected: `remaining internal markers in external columns: 0`

(모델 레벨 `description` 은 내부용이라 검사에서 제외된다 — 위 스크립트의 `i == 0` 조건이 그 역할이다.)

- [ ] **Step 3: dbt parse 재검증**

Task 1 Step 6과 같은 절차(브랜치 detach → parse). Expected: 에러 0, `external models: 7` 유지.
검증 후 `cd ~/ask-seoul/sample/dbt && git checkout dev`.

- [ ] **Step 4: 커밋 + 설계·계획 문서 동승 + PR**

```bash
cd ~/ask-seoul/ASAC-DBT
git add domains/culture/models/gold/_culture_gold__models.yml domains/culture/docs/design/
git commit -m "$(cat <<'EOF'
docs(culture): 외부 gold 7종 컬럼 설명 외부용 정리 + 설계·계획 문서

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
git push -u origin feat/culture-catalog-display
gh pr create --repo ASAC-DE-bigkk/ASAC-DBT --base dev --title "feat(culture): 외부 카탈로그 전시 문구(display 계층) + 설명 잘림 수정"
```

PR body에는 잘림 버그 before/after 1건과 display 블록 예시 1건을 넣는다. 마지막 줄 `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

---

### Task 3: 스냅샷·API 배선 (ASK-Seoul-Dashboard)

**Files:**
- Modify: `extract.py` (신규 함수 + `main()` 의 `tables.append`, `load_basic_meta()`, `extract_basic_domain()`)
- Modify: `app/models.py:28-41`
- Modify: `app/main.py:37-45`

**Interfaces:**
- Consumes: manifest 노드의 `config.meta.display` (Task 1이 만듦)
- Produces: 스냅샷 테이블 레코드의 선택 키 `display_name: str` · `summary: str` · `caveat: str` · `use_cases: list[str]`. **display가 없으면 키 자체가 없다.** T4가 이 키들을 읽는다.

- [ ] **Step 1: 브랜치**

```bash
cd ~/ask-seoul/ASK-Seoul-Dashboard && git checkout dev && git pull
git checkout -b feat/catalog-display-copy
```

- [ ] **Step 2: `display_meta()` 추가**

`extract.py` 의 `is_external()` 정의 바로 아래에 넣는다.

```python
def display_meta(node: dict) -> dict:
    """config.meta.display → 외부 전시 4필드. 선언이 없으면 빈 dict(= 스냅샷에 키 없음 → 화면 폴백)."""
    d = (node.get("config", {}).get("meta", {}) or {}).get("display") or {}
    out: dict = {}
    if d.get("title"):
        out["display_name"] = str(d["title"])
    if d.get("summary"):
        out["summary"] = str(d["summary"])
    if d.get("caveat"):
        out["caveat"] = str(d["caveat"])
    if d.get("use_cases"):
        out["use_cases"] = [str(u) for u in d["use_cases"]]
    return out
```

- [ ] **Step 3: culture 경로에 병합**

`main()` 의 `tables.append({...})` 딕셔너리 **마지막 항목 뒤**에 언팩을 추가한다.

```python
            "lineage": upstream_layers(uid, nodes),
            "sample": sample,
            **display_meta(node),
        })
```

- [ ] **Step 4: basic 도메인 경로에도 같은 구조 열기**

`load_basic_meta()` 의 `lookup[node["name"]] = {...}` 에 두 줄 추가한다. `external` 은
`extract_basic_domain()` 이 이미 `meta.get("external", True)` 로 읽고 있으나 지금은 **아무도 넣지 않아
항상 True** 인 상태다 — 주석이 약속한 동작을 실제로 만든다.

```python
                "lineage": upstream_layers(uid, all_nodes),
                "external": bool(cfg.get("meta", {}).get("external", True)),
                "display": (cfg.get("meta", {}) or {}).get("display") or {},
```

`extract_basic_domain()` 의 `tables.append({...})` 마지막에:

```python
            "sample": sample,
            **display_meta({"config": {"meta": {"display": meta.get("display", {})}}}),
        })
```

- [ ] **Step 5: 응답 계약에 4필드 추가**

`app/models.py` 의 `TableSummary` 에, `description` 아래에 넣는다.

```python
class TableSummary(BaseModel):
    name: str
    domain: str = "culture"
    external: bool = True  # 외부 공개 대상 여부(#269). false=내부/팀 전용(예: SLO 운영 지표)
    relation: str
    description: str = ""
    # 외부 전시 문구(dbt config.meta.display). 선언 없는 테이블은 None → 화면이 name/description 으로 폴백.
    display_name: str | None = None
    summary: str | None = None
    caveat: str | None = None
    use_cases: list[str] = []
    tags: list[str] = []
```

- [ ] **Step 6: `_summary()` 통과**

`app/main.py` 의 `_summary()` 는 키를 명시 나열하므로 새 필드가 그냥은 안 나간다.

```python
def _summary(t: dict) -> dict:
    return {
        **{k: t[k] for k in ("name", "relation", "description", "tags",
                             "contract_enforced", "materialized", "row_count", "date_range")},
        **{k: t[k] for k in ("display_name", "summary", "caveat", "use_cases") if k in t},
        "domain": t.get("domain", "culture"),
        "external": t.get("external", True),
        "column_count": len(t["columns"]),
        "quality_source_count": len(t["quality"]),
    }
```

- [ ] **Step 7: 스냅샷 재생성**

전제: ASAC-DBT PR이 dev에 머지되고 `sample/dbt` 가 dev 최신이며 `dbt docs generate` 가 끝나 있어야 한다.

```bash
cd ~/ask-seoul/sample/dbt && git checkout dev && git pull
cd ~/ask-seoul && MSYS_NO_PATHCONV=1 docker exec elt-infra-airflow-scheduler-1 \
  bash -lc "cd /opt/airflow/dbt/domains/culture && /home/airflow/dbt-venv/bin/dbt docs generate --project-dir . --profiles-dir . --target dev"
cd ~/ask-seoul/ASK-Seoul-Dashboard && .venv/Scripts/python extract.py
```

Expected 마지막 줄: `✓ wrote …catalog_snapshot.json (…, tables=114)`

- [ ] **Step 8: 스냅샷 실측 — 정확히 7개만 display 보유**

```bash
cd ~/ask-seoul/ASK-Seoul-Dashboard
MSYS_NO_PATHCONV=1 PYTHONIOENCODING=utf-8 python -c "
import json
ts = json.load(open('snapshot/catalog_snapshot.json', encoding='utf-8'))['tables']
has = [t for t in ts if 'display_name' in t]
print('total:', len(ts), 'with display:', len(has))
for t in has: print(' ', t['name'], '→', t['display_name'], '| caveat:', 'caveat' in t, '| cases:', len(t.get('use_cases', [])))
print('culture without display:', [t['name'] for t in ts if t['domain']=='culture' and 'display_name' not in t])
"
```

Expected: `total: 114 with display: 7`, 7줄 전부 한글 제목, `caveat: True` 가 2줄(`booking_curve`·`dine_around`) 이상, culture 나머지 7개는 display 없음.

- [ ] **Step 9: 커밋**

```bash
git add extract.py app/models.py app/main.py snapshot/catalog_snapshot.json
git commit -m "$(cat <<'EOF'
feat: dbt meta.display 를 카탈로그 스냅샷·API 로 배선

- extract.display_meta(): title/summary/caveat/use_cases 4필드, 없으면 키 생략
- basic 도메인 meta.external 실제 반영(지금까지 항상 True 였음)
- TableSummary 에 Optional 4필드 + _summary 통과

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: 카드·드로어 렌더 + 실측 (ASK-Seoul-Dashboard)

**Files:**
- Modify: `app/static/index.html` — CSS(카드 제목·caveat·칩), `renderCards()`:568-591, `renderList()`:599-614, `renderTab()`:653-668, 검색 필터:480

**Interfaces:**
- Consumes: 스냅샷/API의 `display_name` · `summary` · `caveat` · `use_cases` (Task 3)

- [ ] **Step 1: CSS 추가**

`.card .nm` 규칙 바로 아래에 넣는다.

```css
  .card .dn { font-size: 15px; font-weight: 700; letter-spacing: -0.01em; line-height: 1.3; }
  .card .nm.sub { font-size: 11px; font-weight: 500; color: var(--ink-3); margin-top: 2px; }
  .caveat { display: flex; gap: 8px; font-size: 12px; line-height: 1.55; color: var(--ink-2);
            background: #fff8e6; border: 1px solid #f0dfae; border-radius: 8px; padding: 10px 12px; }
  .caveat b { color: #8a6a12; font-weight: 700; flex: none; }
  .cases { display: flex; flex-wrap: wrap; gap: 6px; }
  .cases span { font-size: 11.5px; background: var(--chip, #eef2f9); color: var(--ink-2);
                border-radius: 999px; padding: 4px 10px; }
```

- [ ] **Step 2: 카드 제목·본문 교체**

`renderCards()` 의 `.nm`/`.desc` 두 줄을 바꾼다.

```javascript
      <div class="nm">${esc(t.name)}</div>
      <p class="desc">${esc(t.description) || '설명 없음'}</p>
```
↓
```javascript
      ${t.display_name
        ? `<div class="dn">${esc(t.display_name)}</div><div class="nm sub">${esc(t.name)}</div>`
        : `<div class="nm">${esc(t.name)}</div>`}
      <p class="desc">${esc(t.summary || t.description) || '설명 없음'}</p>
```

- [ ] **Step 3: 리스트 뷰도 같은 폴백**

`renderList()` 의 이름·설명 셀:

```javascript
        <div style="min-width:0"><div class="id">${esc(t.display_name || t.name)}</div><div class="ds">${esc(t.summary || t.description) || '설명 없음'}</div></div></div>
```

- [ ] **Step 4: 드로어 Description 섹션에 caveat·use_cases**

`renderTab()` 의 activeTab === 0 첫 줄을 바꾼다.

```javascript
      <section><h3>Description</h3><p class="desc">${esc(t.description) || '—'}</p></section>
```
↓
```javascript
      <section><h3>Description</h3>
        <p class="desc">${esc(t.summary || t.description) || '—'}</p>
        ${t.caveat ? `<div class="caveat" style="margin-top:10px"><b>알아두세요</b><span>${esc(t.caveat)}</span></div>` : ''}
        ${(t.use_cases && t.use_cases.length)
          ? `<div class="cases" style="margin-top:12px">${t.use_cases.map(u => `<span>${esc(u)}</span>`).join('')}</div>` : ''}
      </section>`
```

- [ ] **Step 5: 검색 대상 확장**

480행 필터에 전시 문구를 더한다.

```javascript
    (t.name + ' ' + t.description + ' ' + t.domain + ' ' + ident(t).cat).toLowerCase().includes(q));
```
↓
```javascript
    (t.name + ' ' + (t.display_name || '') + ' ' + (t.summary || '') + ' ' + t.description + ' ' + t.domain + ' ' + ident(t).cat).toLowerCase().includes(q));
```

- [ ] **Step 6: 서버 재기동 + 브라우저 실측**

스냅샷은 임포트 시 1회 로드되므로 재기동이 필수다.

```
preview_stop(현재 serverId) → preview_start({name: "ask-seoul-dashboard"})
```

확인 항목:
1. `/health` 의 `generated_at` 이 방금 시각
2. culture 카드 7개에 한글 제목 + 아래 작은 테이블명
3. `dine_around` 드로어에 "알아두세요" 배너와 활용 예시 칩 3개
4. 검색창에 `미식` 입력 → `dine_around` 1건 히트
5. 내부 마트(`gold_culture_slo_daily`) 카드가 기존과 동일(테이블명 제목 + 내부 pill)
6. `read_console_messages` → 에러 0

- [ ] **Step 7: 스크린샷 + 커밋 + PR**

```bash
git add app/static/index.html
git commit -m "$(cat <<'EOF'
feat: 카탈로그 카드·드로어에 외부 전시 문구 렌더

- 카드 제목 = display_name, 테이블명은 보조 줄로
- 드로어에 caveat 배너 + use_cases 칩
- 검색 대상에 display_name·summary 추가

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
git push -u origin feat/catalog-display-copy
gh pr create --repo ASAC-DE-bigkk/ASK-Seoul-Dashboard --base dev --title "feat: 외부 카탈로그 전시 문구 렌더(display 계층)"
```

---

## 실행 순서 주의

Task 3 Step 7(스냅샷 재생성)은 **Task 2의 PR이 dev에 머지된 뒤**에만 실측이 성립한다.
머지 전에 Task 3~4를 먼저 구현해도 되지만, 검증은 머지 후에 다시 돌린다.
머지는 사용자 지시 사항이다 — 임의로 하지 않는다.
