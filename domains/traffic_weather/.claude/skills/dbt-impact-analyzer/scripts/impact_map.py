#!/usr/bin/env python3
"""manifest child_map 기반 downstream 영향 추출기 (ASAC-DBT#129 traffic_weather 프로토타입).

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
GATE_THRESHOLD = 10  # 초과(>) 시 SKILL.md 3단계가 자동 진행을 멈추고 사용자에게 묻는다
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
                 threshold=GATE_THRESHOLD):
    targets = []
    gate_ids = set()  # 대상 간 공유 downstream 은 union 으로 1회만 센다
    for resolved in resolve_targets(manifest, model_names):
        if not resolved["found"]:
            targets.append(resolved)
            continue
        downstream = downstream_of(manifest, resolved["unique_id"], max_depth)
        gate_ids.update(d["unique_id"] for d in downstream)
        targets.append({"name": resolved["query"],
                        "unique_id": resolved["unique_id"], "found": True,
                        "downstream": downstream,
                        "summary": summarize(downstream)})
    return {"manifest": check_staleness(manifest, project_dir),
            "gate": {"threshold": threshold,
                     "total_downstream": len(gate_ids),
                     "exceeded": len(gate_ids) > threshold},
            "targets": targets}


def main(argv=None):
    # scripts/ -> dbt-impact-analyzer -> skills -> .claude -> domains/traffic_weather
    default_project = Path(__file__).resolve().parents[4]
    p = argparse.ArgumentParser(
        description="dbt manifest 기반 downstream 영향 추출기 (#129 traffic_weather 프로토타입)")
    p.add_argument("--model", nargs="+", required=True,
                   help="수정 대상 모델명(단순명 또는 unique_id)")
    p.add_argument("--project-dir", type=Path, default=default_project,
                   help="신선도 비교 기준 dbt 프로젝트 워킹트리")
    p.add_argument("--manifest", type=Path, default=None,
                   help="manifest.json 경로 (기본: <project-dir>/target/manifest.json)")
    p.add_argument("--max-depth", type=int, default=None, help="BFS 깊이 제한")
    p.add_argument("--threshold", type=int, default=GATE_THRESHOLD,
                   help="게이트 임계값 — downstream union 이 이 값을 초과하면 gate.exceeded")
    args = p.parse_args(argv)
    manifest_path = args.manifest or args.project_dir / "target" / "manifest.json"
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    report = build_report(manifest, args.model, args.project_dir, args.max_depth,
                          threshold=args.threshold)
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
