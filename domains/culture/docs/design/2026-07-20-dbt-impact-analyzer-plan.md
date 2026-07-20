# dbt-impact-analyzer (culture 프로토타입) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** manifest `child_map` 기반 downstream 영향 분석 Claude 스킬(#129)의 culture 스코프 프로토타입 — 결정적 추출기 + SKILL.md 워크플로.

**Architecture:** Python 스크립트(`impact_map.py`, stdlib only)가 BFS로 downstream 목록·메타·신선도를 결정적으로 추출해 JSON 출력 → SKILL.md가 그 결과 위에서 변경 유형 분류·sub-agent 실참조 분석·breaking 판정을 수행. 설계 문서: `domains/culture/docs/design/2026-07-20-dbt-impact-analyzer.md`.

**Tech Stack:** Python 3 stdlib(json/argparse/pathlib/collections/datetime), pytest, dbt manifest v12(dbt 1.10.22).

## Global Constraints

- 스크립트는 **stdlib only** — 서드파티 import 금지
- 스크립트에 **머신 고유 절대경로 하드코딩 금지** (기본값은 스크립트 위치 상향 유도). 이 환경의 manifest 실경로는 SKILL.md 환경 노트에만 기재
- 멘티는 `domains/culture/` 내부만 수정 (레포 루트 `.claude/` 생성 금지 — 그건 #129 본안·멘토 게이트)
- 한국어 출력 명령은 `PYTHONIOENCODING=utf-8` 접두 (cp949 오류 방지)
- 커밋 메시지 마지막 줄: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- PR body 마지막 줄: `🤖 Generated with [Claude Code](https://claude.com/claude-code)`
- PR 셀프 머지 금지 (사용자가 명시 지시할 때만)
- GitHub 이슈는 org 템플릿(`.github/ISSUE_TEMPLATE`) 형식, 라벨 없이 생성('type: task' 라벨은 레포에 없음)
- 임계값 게이트 상수: downstream(테스트 제외) > **10**
- 작업 디렉토리: `C:/Users/Dell3571/ask-seoul/ASAC-DBT` (브랜치 작업 후 dev 복귀)

---

## File Structure

```
domains/culture/
├── .claude/skills/dbt-impact-analyzer/
│   ├── SKILL.md                          # Task 4 — 트리거 + 6단계 워크플로
│   └── scripts/
│       ├── impact_map.py                 # Task 1~2 — BFS 추출기 (stdlib)
│       └── test_impact_map.py            # Task 1~2 — pytest (픽스처 미니 manifest)
└── docs/design/
    ├── 2026-07-20-dbt-impact-analyzer.md      # 설계 (작성됨, 브랜치에서 커밋)
    └── 2026-07-20-dbt-impact-analyzer-plan.md # 본 문서 (브랜치에서 커밋)
```

---

### Task 1: 이슈·브랜치 + BFS 코어 (TDD)

**Files:**
- Create: `domains/culture/.claude/skills/dbt-impact-analyzer/scripts/impact_map.py`
- Create: `domains/culture/.claude/skills/dbt-impact-analyzer/scripts/test_impact_map.py`

**Interfaces:**
- Consumes: dbt manifest dict — `nodes`(`model.*`/`seed.*`/`test.*`), `child_map`, `metadata.generated_at`
- Produces (Task 2·3이 사용):
  - `infer_layer(name: str) -> str` — `silver|int|gold|dim|other`
  - `resolve_targets(manifest: dict, names: list[str]) -> list[dict]` — `{"query","found",("unique_id"|"candidates")}`
  - `downstream_of(manifest: dict, uid: str, max_depth: int|None) -> list[dict]` — depth 오름차순 노드 목록
  - `attached_tests(manifest: dict, uid: str) -> int`
  - `summarize(downstream: list[dict]) -> dict` — `{"total_downstream","by_layer","by_depth"}`

- [ ] **Step 1: 이슈 발행 + 브랜치 생성**

```bash
cd "C:/Users/Dell3571/ask-seoul/ASAC-DBT" && git checkout dev && git pull --ff-only
gh issue create --title "[Feat] dbt-impact-analyzer culture 프로토타입 — manifest 기반 변경 영향 분석 스킬" --body "### 배경 · 목적

#129(멘토 발제, infra 스코프)의 culture 범위 프로토타입. 레포 루트 \`.claude/skills/\` 배치는 공유 인프라 변경(멘토 게이트)이므로, culture 소유 경로(\`domains/culture/.claude/skills/\`)에 먼저 구현·검증 후 #129에 루트 승격을 제안한다. #129는 닫지 않는다.

설계: \`domains/culture/docs/design/2026-07-20-dbt-impact-analyzer.md\`

### 작업 내용 (체크리스트)

- [ ] \`impact_map.py\`: manifest child_map BFS 추출기 (stdlib only, TDD)
- [ ] 신선도 판정(generated_at vs 워킹트리 mtime) + 미발견 후보 제시
- [ ] 실측 스모크: dim_admin_dong downstream 9개 정확 추출
- [ ] \`SKILL.md\`: 트리거 + 6단계 워크플로(임계값 게이트 10, sub-agent 실참조 분석, 리포트 템플릿)
- [ ] E2E: 컬럼 추가(non-breaking)·컬럼 삭제(breaking) 시나리오
- [ ] #129에 프로토타입 PR 링크 코멘트

### 완료 조건 (Acceptance Criteria)

- [ ] pytest 전부 PASS (BFS·테스트 제외·max-depth·dedup·stale·미발견)
- [ ] dim_admin_dong → downstream 9개(테스트 제외) + depth/layer/contract 메타
- [ ] 컬럼 삭제 시나리오 리포트 최상단 ⚠️ BREAKING 경고
- [ ] stale manifest 경고 + 컨테이너 dbt parse 재생성 제안 동작

### 도메인

문화행사 (culture)

### 참고 자료 · 관련 이슈

- #129"
# 출력된 이슈 번호를 <ISSUE>로 기록 (이후 커밋 메시지에 사용)
git checkout -b feat/culture-impact-analyzer
mkdir -p domains/culture/.claude/skills/dbt-impact-analyzer/scripts
```

- [ ] **Step 2: pytest 가용 확인**

Run: `python -m pytest --version`
Expected: 버전 출력. 실패 시 `python -m pip install pytest` 후 재확인.

- [ ] **Step 3: 실패하는 테스트 작성 (BFS 코어)**

`domains/culture/.claude/skills/dbt-impact-analyzer/scripts/test_impact_map.py`:

```python
"""impact_map.py 테스트 — 픽스처 미니 manifest (모델 4·seed 1·테스트 2)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import impact_map


def node(name, rel_path, materialized="table", enforced=False, columns=()):
    return {
        "name": name,
        "path": rel_path,
        "original_file_path": f"models/{rel_path}",
        "config": {"materialized": materialized},
        "contract": {"enforced": enforced},
        "columns": {c: {} for c in columns},
    }


def mini_manifest():
    return {
        "metadata": {"generated_at": "2026-07-20T00:00:00.000000Z"},
        "nodes": {
            "model.culture.silver_a": node("silver_a", "silver/silver_a.sql", columns=("id", "val")),
            "model.culture.int_b": node("int_b", "int/int_b.sql", materialized="ephemeral"),
            "model.culture.gold_c": node("gold_c", "gold/gold_c.sql", enforced=True, columns=("id",)),
            "model.culture.gold_d": node("gold_d", "gold/gold_d.sql"),
            "seed.culture.seed_s": node("seed_s", "seed_s.csv", materialized="seed"),
            "test.culture.t_b": {"name": "t_b"},
            "test.culture.t_c": {"name": "t_c"},
        },
        "child_map": {
            "seed.culture.seed_s": ["model.culture.silver_a"],
            "model.culture.silver_a": ["model.culture.int_b", "model.culture.gold_d"],
            "model.culture.int_b": ["model.culture.gold_c", "test.culture.t_b"],
            "model.culture.gold_c": ["test.culture.t_c"],
            "model.culture.gold_d": [],
        },
    }


def test_bfs_depth_layer_meta():
    m = mini_manifest()
    ds = impact_map.downstream_of(m, "model.culture.silver_a", None)
    assert [(d["name"], d["depth"]) for d in ds] == [
        ("gold_d", 1), ("int_b", 1), ("gold_c", 2)]
    gold_c = next(d for d in ds if d["name"] == "gold_c")
    assert gold_c["layer"] == "gold"
    assert gold_c["contract_enforced"] is True
    assert gold_c["columns"] == ["id"]
    assert gold_c["materialization"] == "table"
    assert gold_c["path"] == "models/gold/gold_c.sql"


def test_tests_excluded_but_counted():
    m = mini_manifest()
    ds = impact_map.downstream_of(m, "model.culture.silver_a", None)
    assert all(not d["unique_id"].startswith("test.") for d in ds)
    assert next(d for d in ds if d["name"] == "int_b")["attached_tests"] == 1
    assert next(d for d in ds if d["name"] == "gold_d")["attached_tests"] == 0


def test_max_depth_limits_traversal():
    m = mini_manifest()
    ds = impact_map.downstream_of(m, "model.culture.silver_a", 1)
    assert sorted(d["name"] for d in ds) == ["gold_d", "int_b"]


def test_dedup_keeps_min_depth():
    m = mini_manifest()
    m["child_map"]["model.culture.silver_a"].append("model.culture.gold_c")
    ds = impact_map.downstream_of(m, "model.culture.silver_a", None)
    assert next(d for d in ds if d["name"] == "gold_c")["depth"] == 1
    assert len([d for d in ds if d["name"] == "gold_c"]) == 1


def test_seed_traversal_reaches_models():
    m = mini_manifest()
    ds = impact_map.downstream_of(m, "seed.culture.seed_s", None)
    assert next(d for d in ds if d["name"] == "silver_a")["depth"] == 1
    assert len(ds) == 4


def test_infer_layer():
    assert impact_map.infer_layer("silver_culture_event") == "silver"
    assert impact_map.infer_layer("int_culture_activity_days") == "int"
    assert impact_map.infer_layer("gold_culture_qa_eval") == "gold"
    assert impact_map.infer_layer("dim_admin_dong") == "dim"
    assert impact_map.infer_layer("seed_s") == "other"


def test_summarize():
    m = mini_manifest()
    s = impact_map.summarize(impact_map.downstream_of(m, "model.culture.silver_a", None))
    assert s == {"total_downstream": 3,
                 "by_layer": {"gold": 2, "int": 1},
                 "by_depth": {"1": 2, "2": 1}}


def test_resolve_simple_name_and_unique_id():
    m = mini_manifest()
    r = impact_map.resolve_targets(m, ["silver_a", "model.culture.gold_c"])
    assert r[0] == {"query": "silver_a", "found": True, "unique_id": "model.culture.silver_a"}
    assert r[1]["unique_id"] == "model.culture.gold_c"
```

- [ ] **Step 4: 실패 확인**

Run: `cd "C:/Users/Dell3571/ask-seoul/ASAC-DBT/domains/culture/.claude/skills/dbt-impact-analyzer/scripts" && python -m pytest test_impact_map.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'impact_map'`

- [ ] **Step 5: 최소 구현**

`domains/culture/.claude/skills/dbt-impact-analyzer/scripts/impact_map.py`:

```python
#!/usr/bin/env python3
"""manifest child_map 기반 downstream 영향 추출기 (ASAC-DBT#129 culture 프로토타입).

stdlib only. 결정적 추출만 담당 — 실참조·breaking 의미 판정은 SKILL.md의
sub-agent 단계가 수행한다.
"""
import argparse
import json
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

TRAVERSABLE = ("model.", "seed.")
LAYER_PREFIXES = (("silver_", "silver"), ("int_", "int"), ("gold_", "gold"), ("dim_", "dim"))


def infer_layer(name):
    for prefix, layer in LAYER_PREFIXES:
        if name.startswith(prefix):
            return layer
    return "other"


def resolve_targets(manifest, names):
    """이름(단순명 또는 unique_id) -> 노드. 미발견 시 부분일치 후보 최대 10개."""
    nodes = manifest["nodes"]
    by_name = {n["name"]: uid for uid, n in nodes.items() if uid.startswith(TRAVERSABLE)}
    out = []
    for name in names:
        uid = name if name in nodes else by_name.get(name)
        if uid is None:
            candidates = sorted(n for n in by_name if name.lower() in n.lower())[:10]
            out.append({"query": name, "found": False, "candidates": candidates})
        else:
            out.append({"query": name, "found": True, "unique_id": uid})
    return out


def attached_tests(manifest, uid):
    return sum(1 for c in manifest.get("child_map", {}).get(uid, [])
               if c.startswith("test."))


def downstream_of(manifest, uid, max_depth):
    """child_map BFS. 테스트 노드 제외, 중복은 최소 depth 채택.

    반환 정렬: (depth, unique_id) 오름차순.
    """
    child_map = manifest.get("child_map", {})
    nodes = manifest["nodes"]
    seen = {}
    queue = deque([(uid, 0)])
    while queue:
        cur, depth = queue.popleft()
        if max_depth is not None and depth >= max_depth:
            continue
        for child in child_map.get(cur, []):
            if not child.startswith(TRAVERSABLE) or child not in nodes or child in seen:
                continue
            seen[child] = depth + 1
            queue.append((child, depth + 1))
    result = []
    for cid in sorted(seen, key=lambda c: (seen[c], c)):
        node = nodes[cid]
        result.append({
            "name": node["name"],
            "unique_id": cid,
            "depth": seen[cid],
            "layer": infer_layer(node["name"]),
            "materialization": node.get("config", {}).get("materialized"),
            "contract_enforced": bool((node.get("contract") or {}).get("enforced")),
            "columns": sorted(node.get("columns") or {}),
            "path": node.get("original_file_path") or node.get("path", ""),
            "attached_tests": attached_tests(manifest, cid),
        })
    return result


def summarize(downstream):
    by_layer, by_depth = {}, {}
    for d in downstream:
        by_layer[d["layer"]] = by_layer.get(d["layer"], 0) + 1
        by_depth[str(d["depth"])] = by_depth.get(str(d["depth"]), 0) + 1
    return {"total_downstream": len(downstream),
            "by_layer": by_layer, "by_depth": by_depth}
```

- [ ] **Step 6: 통과 확인**

Run: `python -m pytest test_impact_map.py -v` (같은 디렉토리)
Expected: 8 passed

- [ ] **Step 7: 커밋**

```bash
cd "C:/Users/Dell3571/ask-seoul/ASAC-DBT"
git add domains/culture/.claude/skills/dbt-impact-analyzer/scripts/
git commit -m "feat(culture): #<ISSUE> impact_map BFS 코어 — child_map 순회·테스트 제외·layer 메타

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: 신선도 판정 + 리포트 조립 + CLI

**Files:**
- Modify: `domains/culture/.claude/skills/dbt-impact-analyzer/scripts/impact_map.py` (함수 추가)
- Modify: `domains/culture/.claude/skills/dbt-impact-analyzer/scripts/test_impact_map.py` (테스트 추가)

**Interfaces:**
- Consumes: Task 1의 `resolve_targets`/`downstream_of`/`summarize`
- Produces:
  - `check_staleness(manifest: dict, project_dir: Path) -> dict` — `{"generated_at","stale","stale_files"}`
  - `build_report(manifest: dict, model_names: list[str], project_dir: Path, max_depth: int|None) -> dict` — 설계 문서의 출력 JSON 스키마
  - `main(argv: list[str]|None) -> int` — CLI 엔트리(`--model`/`--project-dir`/`--manifest`/`--max-depth`)

- [ ] **Step 1: 실패하는 테스트 추가**

`test_impact_map.py` 하단에 추가:

```python
def _write_project(tmp_path, sql_name="silver/x.sql"):
    d = tmp_path / "models" / Path(sql_name).parent
    d.mkdir(parents=True, exist_ok=True)
    (tmp_path / "models" / sql_name).write_text("select 1", encoding="utf-8")
    return tmp_path


def test_stale_when_file_newer_than_manifest(tmp_path):
    m = mini_manifest()
    # 과거 고정값 — 실행 시각·시간대와 무관하게 파일 mtime(지금)이 항상 더 최신
    m["metadata"]["generated_at"] = "2020-01-01T00:00:00.000000Z"
    proj = _write_project(tmp_path)
    r = impact_map.check_staleness(m, proj)
    assert r["stale"] is True
    assert r["stale_files"] == ["models/silver/x.sql"]
    assert r["generated_at"] == "2020-01-01T00:00:00.000000Z"


def test_fresh_when_manifest_newer(tmp_path):
    m = mini_manifest()
    m["metadata"]["generated_at"] = "2099-01-01T00:00:00.000000Z"
    proj = _write_project(tmp_path)
    r = impact_map.check_staleness(m, proj)
    assert r["stale"] is False
    assert r["stale_files"] == []


def test_not_found_gives_candidates():
    m = mini_manifest()
    r = impact_map.resolve_targets(m, ["gold"])
    assert r[0]["found"] is False
    assert r[0]["candidates"] == ["gold_c", "gold_d"]


def test_build_report_shape(tmp_path):
    m = mini_manifest()
    m["metadata"]["generated_at"] = "2099-01-01T00:00:00.000000Z"
    proj = _write_project(tmp_path)
    r = impact_map.build_report(m, ["silver_a", "nope"], proj, None)
    assert r["manifest"]["stale"] is False
    assert r["targets"][0]["summary"]["total_downstream"] == 3
    assert r["targets"][1] == {"query": "nope", "found": False, "candidates": []}


def test_cli_smoke(tmp_path, capsys):
    import json as _json
    m = mini_manifest()
    m["metadata"]["generated_at"] = "2099-01-01T00:00:00.000000Z"
    proj = _write_project(tmp_path)
    (proj / "target").mkdir()
    (proj / "target" / "manifest.json").write_text(
        _json.dumps(m), encoding="utf-8")
    rc = impact_map.main(["--model", "silver_a", "--project-dir", str(proj)])
    assert rc == 0
    out = _json.loads(capsys.readouterr().out)
    assert out["targets"][0]["summary"]["total_downstream"] == 3
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest test_impact_map.py -v`
Expected: 기존 8 passed + 신규 5 FAIL — `AttributeError: ... 'check_staleness'`

- [ ] **Step 3: 구현 — `summarize` 아래에 추가**

```python
def check_staleness(manifest, project_dir):
    """manifest generated_at vs 워킹트리 models/seeds 파일 mtime 비교."""
    raw = manifest["metadata"]["generated_at"]
    gen = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    stale_files = []
    project_dir = Path(project_dir)
    for pattern in ("models/**/*.sql", "models/**/*.yml", "seeds/**/*"):
        for f in sorted(project_dir.glob(pattern)):
            if not f.is_file():
                continue
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if mtime > gen:
                stale_files.append(str(f.relative_to(project_dir)).replace("\\", "/"))
    return {"generated_at": raw, "stale": bool(stale_files),
            "stale_files": stale_files[:10]}


def build_report(manifest, model_names, project_dir, max_depth):
    targets = []
    for resolved in resolve_targets(manifest, model_names):
        if not resolved["found"]:
            targets.append(resolved)
            continue
        downstream = downstream_of(manifest, resolved["unique_id"], max_depth)
        targets.append({"name": resolved["query"],
                        "unique_id": resolved["unique_id"], "found": True,
                        "downstream": downstream,
                        "summary": summarize(downstream)})
    return {"manifest": check_staleness(manifest, project_dir),
            "targets": targets}


def main(argv=None):
    # scripts/ -> dbt-impact-analyzer -> skills -> .claude -> domains/culture
    default_project = Path(__file__).resolve().parents[4]
    p = argparse.ArgumentParser(
        description="dbt manifest 기반 downstream 영향 추출기 (#129 culture 프로토타입)")
    p.add_argument("--model", nargs="+", required=True,
                   help="수정 대상 모델명(단순명 또는 unique_id)")
    p.add_argument("--project-dir", type=Path, default=default_project,
                   help="신선도 비교 기준 dbt 프로젝트 워킹트리")
    p.add_argument("--manifest", type=Path, default=None,
                   help="manifest.json 경로 (기본: <project-dir>/target/manifest.json)")
    p.add_argument("--max-depth", type=int, default=None, help="BFS 깊이 제한")
    args = p.parse_args(argv)
    manifest_path = args.manifest or args.project_dir / "target" / "manifest.json"
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    report = build_report(manifest, args.model, args.project_dir, args.max_depth)
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest test_impact_map.py -v`
Expected: 13 passed

- [ ] **Step 5: 커밋**

```bash
cd "C:/Users/Dell3571/ask-seoul/ASAC-DBT"
git add domains/culture/.claude/skills/dbt-impact-analyzer/scripts/
git commit -m "feat(culture): #<ISSUE> impact_map 신선도 판정 + 리포트 CLI

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: 실측 스모크 — 실제 culture manifest 대조

**Files:**
- 없음 (검증 전용 — 산출물은 실행 결과 기록)

**Interfaces:**
- Consumes: Task 2의 CLI. 실측 manifest = `C:/Users/Dell3571/ask-seoul/sample/dbt/domains/culture/target/manifest.json` (2026-07-20 빌드분)

- [ ] **Step 1: dim_admin_dong — 설계 AC 1 (downstream 9개)**

```bash
cd "C:/Users/Dell3571/ask-seoul/ASAC-DBT/domains/culture/.claude/skills/dbt-impact-analyzer/scripts"
PYTHONIOENCODING=utf-8 python impact_map.py --model dim_admin_dong \
  --manifest "C:/Users/Dell3571/ask-seoul/sample/dbt/domains/culture/target/manifest.json" \
  | python -c "import json,sys; r=json.load(sys.stdin); t=r['targets'][0]; print('total:', t['summary']['total_downstream']); [print(' ', d['depth'], d['layer'], d['name']) for d in t['downstream']]"
```

Expected: **depth=1 행이 9개** — 탐색(IA-1) fanout 실측치와 일치(전이 포함 total은 20).
불일치 시: manifest 재확인(`generated_at`이 2026-07-20인지) 후 원인 규명 — 숫자를 맞추기 위한 코드 수정 금지(실측이 진실).
(실행 기록: total 20 = gold 9·silver 10·int 1, depth=1은 정확히 9 — child_map 직접 대조로 독립 검증됨.)

- [ ] **Step 2: int_culture_activity_days → activity_by_dong 포함 확인 (E2E 대비)**

```bash
PYTHONIOENCODING=utf-8 python impact_map.py --model int_culture_activity_days silver_culture_performance \
  --manifest "C:/Users/Dell3571/ask-seoul/sample/dbt/domains/culture/target/manifest.json" \
  | python -c "import json,sys; r=json.load(sys.stdin); [print(t['name'], '->', [d['name'] for d in t['downstream']]) for t in r['targets']]"
```

Expected: `int_culture_activity_days`의 downstream에 `gold_culture_activity_by_dong` 포함, `silver_culture_performance`는 5개(IA-1 실측).

- [ ] **Step 3: 신선도 — stale 판정 라이브 확인**

```bash
PYTHONIOENCODING=utf-8 python impact_map.py --model dim_admin_dong \
  --manifest "C:/Users/Dell3571/ask-seoul/sample/dbt/domains/culture/target/manifest.json" \
  --project-dir "C:/Users/Dell3571/ask-seoul/ASAC-DBT/domains/culture" \
  | python -c "import json,sys; m=json.load(sys.stdin)['manifest']; print('stale:', m['stale'], m['stale_files'][:3])"
```

Expected: `stale: True` + docs/design 제외한 models/seeds 중 오늘 만진 파일 목록(오늘 설계 문서만 만졌다면 `stale: False`). 출력이 판정 로직과 정합인지 확인만 — 값 자체는 워킹트리 상태에 따름.

- [ ] **Step 4: 결과를 이슈 코멘트로 기록**

```bash
cd "C:/Users/Dell3571/ask-seoul/ASAC-DBT"
gh issue comment <ISSUE> --body "실측 스모크: dim_admin_dong downstream 9개(테스트 제외) 정확 추출, int_culture_activity_days→gold_culture_activity_by_dong 식별, silver_culture_performance 5개. stale 판정 동작 확인."
```

---

### Task 4: SKILL.md 작성

**Files:**
- Create: `domains/culture/.claude/skills/dbt-impact-analyzer/SKILL.md`

**Interfaces:**
- Consumes: Task 2 CLI의 출력 JSON 스키마(`manifest.stale`, `targets[].summary.total_downstream`, `targets[].downstream[]`)

- [ ] **Step 1: SKILL.md 작성**

```markdown
---
name: dbt-impact-analyzer
description: Use when modifying dbt models in domains/culture (or when the user asks for change-impact analysis) — extracts downstream lineage from manifest child_map deterministically, then judges breaking risk per column via sub-agents. ASAC-DBT#129 culture prototype.
---

# dbt-impact-analyzer (culture 프로토타입)

dbt 모델 수정 **전에** downstream 영향을 파악한다. 추출은 스크립트가 결정적으로,
판정은 sub-agent가 SQL 실참조 기준으로 수행한다. 설계:
`domains/culture/docs/design/2026-07-20-dbt-impact-analyzer.md` (이슈 #129 참조).

## 환경 노트 (이 레포 전용)

- manifest는 컨테이너 빌드 산출물 — 이 환경 실경로:
  `C:/Users/Dell3571/ask-seoul/sample/dbt/domains/culture/target/manifest.json`
  (ASAC-DBT 워킹트리는 `target/` gitignore). 반드시 `--manifest`로 전달.
- 재파싱(빌드 아님, ~10초):
  `MSYS_NO_PATHCONV=1 docker exec elt-infra-airflow-scheduler-1 bash -c "cd /opt/airflow/dbt/domains/culture && /home/airflow/dbt-venv/bin/dbt parse --project-dir . --profiles-dir . --target dev"`
  실행 후 sample/dbt 체크아웃이 dev 기준이면 그대로, 다른 브랜치 검증 중이면 해당 브랜치 파일 기준으로 재생성됨에 유의.

## 워크플로 (순서 고정)

1. **수정 대상 식별**: `git diff --name-only dev` + unstaged에서
   `domains/culture/models/**/*.sql|yml` 추출. diff가 없으면 사용자가 지목한
   모델을 사용(가정 시나리오 분석 허용 — 이때 리포트에 "가정" 명시).
2. **추출**: `PYTHONIOENCODING=utf-8 python <이 스킬 디렉토리>/scripts/impact_map.py
   --model <names> --manifest <환경 노트 경로>`.
   `manifest.stale == true`면: 경고 표시(stale_files 목록) → 사용자에게 재파싱
   (환경 노트 커맨드) 승인을 물은 뒤, 승인 시 재파싱+재추출, 거절 시
   리포트에 "stale manifest 기준" 명시하고 진행.
3. **임계값 게이트**: 대상 모델 합산 `total_downstream`(테스트 제외) > **10**이면
   자동 진행 금지 — AskUserQuestion으로 ①대상 모델 축소 ②`--max-depth` 제한
   ③전체 계속 중 선택받는다.
4. **변경 유형 분류**: 대상 모델 SQL·yml diff(가정 시나리오면 사용자 서술)에서
   컬럼 추가 / 컬럼 삭제 / 타입 변경 / 로직 변경(스키마 불변)을 구분하고,
   삭제·타입 변경된 컬럼명 목록을 확정한다.
5. **sub-agent 실참조 분석** (컬럼 삭제·타입 변경이 있을 때만): downstream 모델별로
   Agent tool 병렬 dispatch. 각 agent 입력은 (모델 SQL 워킹트리 경로, 변경 컬럼
   목록, upstream 모델명)만 — 세션 히스토리 전달 금지. agent는 SQL을 읽고
   컬럼별 판정만 반환: `명시 참조`(select/join/where/group by에 등장) /
   `select * 전파` / `미참조`.
6. **리포트**: 아래 템플릿. breaking 1건이라도 있으면 ⚠️ 블록 최상단.

## 판정 규칙 (governed)

| 판정 | 조건 |
|---|---|
| breaking | 삭제/타입 변경 컬럼을 downstream이 명시 참조 또는 `select *` 전파, 또는 대상 모델이 contract enforced인데 계약 컬럼을 삭제/타입 변경 |
| warn | 로직 변경(스키마 불변, 값 변화 가능) — downstream `attached_tests` 수 첨부 |
| non-breaking | 컬럼 추가, 삭제/변경 컬럼을 downstream이 미참조 |

## 리포트 템플릿

    ## 영향 분석: <model> (<변경 유형>)
    ⚠️ BREAKING: <n>건 — <모델 목록>        ← breaking 있을 때만, 최상단

    | downstream | depth | 영향 유형 | 참조 방식 | 위험도 | 비고 |
    |---|---|---|---|---|---|
    | gold_x | 1 | 직접 참조 | 명시(col_a) | breaking | contract enforced |
    | gold_y | 2 | 간접 전파 | select * | warn | 테스트 4개 |

    manifest: <generated_at> (stale 여부) · downstream 합계 <n> (테스트 제외)

- 영향 유형: depth=1 → 직접 참조, depth>=2 → 간접 전파
- 비고: contract enforced 여부, attached_tests 수, 가정 시나리오 여부

## 한계 (프로토타입)

- culture 프로젝트 한정 — 루트 승격은 #129 본안(멘토 게이트)
- raw SQL 기준 실참조 판정(compiled 미사용) — dbt_utils 매크로가 컬럼을 숨기는
  경우 sub-agent가 `매크로 경유 가능`으로 보고하고 사람 확인 요청
- exposure 노드 추적 없음(culture manifest에 현행 exposure 없음)
```

- [ ] **Step 2: 스킬 인식 확인**

새 파일이 디렉토리 스코프 스킬(`domains/culture:dbt-impact-analyzer`)로 잡히는지는
세션 재시작 후에만 보이므로, 이 단계에서는 파일 배치·frontmatter 문법만 검수:
`name`이 디렉토리명과 일치, description이 트리거 조건 서술 포함.

- [ ] **Step 3: 커밋 (설계·계획 문서 포함)**

```bash
cd "C:/Users/Dell3571/ask-seoul/ASAC-DBT"
git add domains/culture/.claude/skills/dbt-impact-analyzer/SKILL.md \
  domains/culture/docs/design/2026-07-20-dbt-impact-analyzer.md \
  domains/culture/docs/design/2026-07-20-dbt-impact-analyzer-plan.md
git commit -m "feat(culture): #<ISSUE> dbt-impact-analyzer SKILL.md + 설계·계획 문서

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: E2E 시나리오 2건 + PR + #129 코멘트

**Files:**
- 없음 (검증·운영 전용)

**Interfaces:**
- Consumes: Task 2 CLI + Task 4 SKILL.md 워크플로(가정 시나리오 경로)

- [ ] **Step 1: E2E ① — 컬럼 추가(non-breaking, PR#281 재현)**

SKILL.md 워크플로를 가정 시나리오로 수행: "`int_culture_activity_days`에
`is_free` 컬럼을 **추가**한다"로 1~6단계 실행(5단계는 컬럼 추가라 skip 조건 충족).
Expected: downstream에 `gold_culture_activity_by_dong` 식별, 판정 non-breaking,
리포트에 ⚠️ 블록 없음, "가정" 명시.

- [ ] **Step 2: E2E ② — 컬럼 삭제(breaking)**

가정 시나리오: "`silver_culture_performance`에서 `genre` 컬럼을 **삭제**한다"로
1~6단계 실행. 5단계에서 downstream 5개 모델 각각에 sub-agent dispatch —
`genre` 실참조 여부 판정(venue_profile은 `max_by(genre, n)` 사용이 이번 주
작업으로 알려져 있으나, **판정은 agent가 SQL을 읽고 내린 결과만 사용**).
Expected: 리포트 최상단 ⚠️ BREAKING + 실참조 모델 명시(venue_profile 포함),
미참조 downstream은 non-breaking 구분.

- [ ] **Step 3: E2E 결과를 이슈에 기록**

```bash
cd "C:/Users/Dell3571/ask-seoul/ASAC-DBT"
gh issue comment <ISSUE> --body "E2E: ① int_culture_activity_days 컬럼 추가 → activity_by_dong 식별·non-breaking. ② silver_culture_performance.genre 삭제 → ⚠️ BREAKING <n>건(실참조: <목록>). 리포트 템플릿 정합."
```

- [ ] **Step 4: PR 생성 (base dev)**

```bash
git push -u origin feat/culture-impact-analyzer
gh pr create --base dev --title "feat(culture): #<ISSUE> dbt-impact-analyzer culture 프로토타입" --body "## 요약
- #129(infra 스코프, 멘토 발제)의 culture 범위 프로토타입 — \`domains/culture/.claude/skills/dbt-impact-analyzer/\`
- \`impact_map.py\`: manifest child_map BFS 추출기(stdlib only, pytest 13개)
- \`SKILL.md\`: 6단계 워크플로 — stale 경고+재파싱 제안, 임계값 게이트(>10), sub-agent 실참조 분석, breaking 리포트

## 실측
- dim_admin_dong → downstream 9개(테스트 제외) 정확 추출
- E2E: 컬럼 추가(non-breaking)·genre 삭제(⚠️ BREAKING) 시나리오 통과

## 참고
- 설계: domains/culture/docs/design/2026-07-20-dbt-impact-analyzer.md
- Closes #<ISSUE> · Refs #129 (닫지 않음 — 루트 승격은 멘토 게이트)

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

- [ ] **Step 5: #129에 프로토타입 링크 코멘트**

```bash
gh issue comment 129 --body "culture 스코프 프로토타입 구현했습니다: <PR URL>
- 배치: domains/culture/.claude/skills/ (culture 소유 경로 — 루트 승격 전 검증용)
- 스크립트는 머신 경로 하드코딩 없이 이식 가능(--manifest 인자) — 루트 승격 시 그대로 재사용 가능합니다
- 실측: dim_admin_dong downstream 9개 추출, 컬럼 삭제 시나리오 ⚠️ BREAKING 리포트 동작
검토 후 루트 .claude/skills/ 승격 판단 부탁드립니다."
```

- [ ] **Step 6: dev 복귀**

```bash
git checkout dev
```

(머지는 사용자/멘토 판단 — 셀프 머지 금지.)
