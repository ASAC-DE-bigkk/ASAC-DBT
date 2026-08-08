#!/usr/bin/env python3
"""manifest child_map 기반 downstream 영향 추출기 (ASAC-DBT#129 culture 프로토타입).

stdlib only. 결정적 추출만 담당 — 실참조·breaking 의미 판정은 SKILL.md의
sub-agent 단계가 수행한다.
"""
import argparse
import json
import re
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

TRAVERSABLE = ("model.", "seed.")
GATE_THRESHOLD = 10  # 초과(>) 시 SKILL.md 3단계가 자동 진행을 멈추고 사용자에게 묻는다
LAYER_PREFIXES = (("silver_", "silver"), ("int_", "int"), ("gold_", "gold"), ("dim_", "dim"))

# 크로스도메인 스캔이 훑는 파일 (다른 도메인의 워킹트리)
CROSS_GLOBS = ("models/**/*.sql", "models/**/*.yml", "models/**/*.yaml")
# 빌드 산출물·패키지는 원본이 아니다 — 여기 걸리면 같은 참조를 두 번 세거나
# 컴파일된 사본을 "선언"으로 오독한다.
CROSS_SKIP_PARTS = frozenset({"target", "dbt_packages", "dbt_modules", ".venv", "__pycache__"})


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


def _no_scan(reason):
    """스캔을 못 한 경우에도 **같은 모양**을 돌려준다 — 소비자가 `total` 을 읽다
    환경에 따라 KeyError 를 맞으면, 그건 "참조 0건"과 구분이 안 된다."""
    return {"scanned": False, "reason": reason, "scanned_domains": [],
            "total": 0, "by_domain": {}, "refs": []}


def _scannable(path):
    return not (CROSS_SKIP_PARTS & set(path.parts))


def cross_domain_refs(project_dir, model_names, domains_root=None):
    """다른 도메인 워킹트리에서 이 모델들을 **이름으로** 찾는다 (manifest 밖 영역).

    🔑 왜 manifest 로 못 하나: 도메인마다 dbt 프로젝트가 독립이라, 남이 우리 모델을
    `source()` 로 읽는 선언은 **그쪽 sources.yml** 에 있고 우리 manifest 의 child_map
    에는 존재하지 않는다. 그래서 downstream 이 0 으로 나온다 — 없는 게 아니라 안 보인다.

    실사고(2026-08-08): citydata 가 `gold_citydata_ppltn_by_time` 을 "미사용"으로 지웠는데
    culture 가 읽고 있어 prod 야간 배치가 깨졌다. 그쪽 검증은 전부 통과한 상태였다.

    **source alias 가 아니라 모델명으로 찾는다.** alias 는 도메인마다 제각각이라
    (`culture` · `citydata_gold` · `seoul_citydata` …) 그걸 키로 삼으면 놓친다.
    `source('x','<이름>')` 도 sources.yml 의 `- name: <이름>` 도 같은 한 패턴에 잡힌다.
    """
    project_dir = Path(project_dir).resolve()
    root = Path(domains_root).resolve() if domains_root else project_dir.parent
    if not root.is_dir():
        return _no_scan(f"도메인 루트 없음: {root}")

    others = sorted(d for d in root.iterdir()
                    if d.is_dir() and d.resolve() != project_dir and (d / "models").is_dir())
    if not others:
        return _no_scan(f"다른 도메인 없음: {root}")

    # 단어 경계로 묶어 부분일치를 막는다 — `gold_x` 가 `gold_x_daily` 에 걸리면 안 된다.
    pattern = re.compile(r"\b(" + "|".join(re.escape(n) for n in model_names) + r")\b")
    refs = []
    for domain in others:
        for glob in CROSS_GLOBS:
            for f in sorted(domain.glob(glob)):
                if not (f.is_file() and _scannable(f)):
                    continue
                try:
                    text = f.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue    # 읽을 수 없는 파일 하나가 스캔 전체를 죽이지 않는다
                if not pattern.search(text):
                    continue
                for lineno, line in enumerate(text.splitlines(), 1):
                    for name in set(pattern.findall(line)):
                        refs.append({
                            "model": name,
                            "domain": domain.name,
                            "file": str(f.relative_to(root)).replace("\\", "/"),
                            "line": lineno,
                            "text": line.strip()[:160],
                        })
    refs.sort(key=lambda r: (r["model"], r["domain"], r["file"], r["line"]))
    return {"scanned": True,
            "scanned_domains": [d.name for d in others],
            "total": len(refs),
            "by_domain": {d: sum(1 for r in refs if r["domain"] == d)
                          for d in sorted({r["domain"] for r in refs})},
            "refs": refs}


def summarize(downstream):
    by_layer, by_depth = {}, {}
    for d in downstream:
        by_layer[d["layer"]] = by_layer.get(d["layer"], 0) + 1
        by_depth[str(d["depth"])] = by_depth.get(str(d["depth"]), 0) + 1
    return {"total_downstream": len(downstream),
            "by_layer": by_layer, "by_depth": by_depth}


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


def build_report(manifest, model_names, project_dir, max_depth,
                 threshold=GATE_THRESHOLD, domains_root=None, scan_cross=True):
    targets = []
    gate_ids = set()  # 대상 간 공유 downstream 은 union 으로 1회만 센다
    resolved_names = []
    for resolved in resolve_targets(manifest, model_names):
        if not resolved["found"]:
            targets.append(resolved)
            continue
        downstream = downstream_of(manifest, resolved["unique_id"], max_depth)
        gate_ids.update(d["unique_id"] for d in downstream)
        # 크로스도메인 스캔의 대상은 **수정 모델 + 그 downstream 전부**다. 남이 읽는 것이
        # 대상 모델 자신이 아니라 그 하류일 수 있다(실사고: transit → gold_culture_event_schedule).
        resolved_names.append(manifest["nodes"][resolved["unique_id"]]["name"])
        resolved_names.extend(d["name"] for d in downstream)
        targets.append({"name": resolved["query"],
                        "unique_id": resolved["unique_id"], "found": True,
                        "downstream": downstream,
                        "summary": summarize(downstream)})

    cross = ({"scanned": False, "reason": "--no-cross-scan", "refs": []}
             if not scan_cross or not resolved_names
             else cross_domain_refs(project_dir, sorted(set(resolved_names)), domains_root))
    return {"manifest": check_staleness(manifest, project_dir),
            "gate": {"threshold": threshold,
                     "total_downstream": len(gate_ids),
                     "exceeded": len(gate_ids) > threshold},
            "cross_domain": cross,
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
    p.add_argument("--threshold", type=int, default=GATE_THRESHOLD,
                   help="게이트 임계값 — downstream union 이 이 값을 초과하면 gate.exceeded")
    p.add_argument("--domains-root", type=Path, default=None,
                   help="도메인들이 모인 디렉토리 (기본: <project-dir>의 부모)")
    p.add_argument("--no-cross-scan", action="store_true",
                   help="크로스도메인 스캔 생략 — 남이 이 모델을 읽는지 확인하지 않는다")
    args = p.parse_args(argv)
    manifest_path = args.manifest or args.project_dir / "target" / "manifest.json"
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    report = build_report(manifest, args.model, args.project_dir, args.max_depth,
                          threshold=args.threshold, domains_root=args.domains_root,
                          scan_cross=not args.no_cross_scan)
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
