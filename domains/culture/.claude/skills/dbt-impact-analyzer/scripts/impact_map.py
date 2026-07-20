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
