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
            "model.asac_seoul.silver_a": node("silver_a", "silver/silver_a.sql", columns=("id", "val")),
            "model.asac_seoul.int_b": node("int_b", "int/int_b.sql", materialized="ephemeral"),
            "model.asac_seoul.gold_c": node("gold_c", "gold/gold_c.sql", enforced=True, columns=("id",)),
            "model.asac_seoul.gold_d": node("gold_d", "gold/gold_d.sql"),
            "seed.asac_seoul.seed_s": node("seed_s", "seed_s.csv", materialized="seed"),
            "test.asac_seoul.t_b": {"name": "t_b"},
            "test.asac_seoul.t_c": {"name": "t_c"},
        },
        "child_map": {
            "seed.asac_seoul.seed_s": ["model.asac_seoul.silver_a"],
            "model.asac_seoul.silver_a": ["model.asac_seoul.int_b", "model.asac_seoul.gold_d"],
            "model.asac_seoul.int_b": ["model.asac_seoul.gold_c", "test.asac_seoul.t_b"],
            "model.asac_seoul.gold_c": ["test.asac_seoul.t_c"],
            "model.asac_seoul.gold_d": [],
        },
    }


def test_bfs_depth_layer_meta():
    m = mini_manifest()
    ds = impact_map.downstream_of(m, "model.asac_seoul.silver_a", None)
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
    ds = impact_map.downstream_of(m, "model.asac_seoul.silver_a", None)
    assert all(not d["unique_id"].startswith("test.") for d in ds)
    assert next(d for d in ds if d["name"] == "int_b")["attached_tests"] == 1
    assert next(d for d in ds if d["name"] == "gold_d")["attached_tests"] == 0


def test_max_depth_limits_traversal():
    m = mini_manifest()
    ds = impact_map.downstream_of(m, "model.asac_seoul.silver_a", 1)
    assert sorted(d["name"] for d in ds) == ["gold_d", "int_b"]


def test_dedup_keeps_min_depth():
    m = mini_manifest()
    m["child_map"]["model.asac_seoul.silver_a"].append("model.asac_seoul.gold_c")
    ds = impact_map.downstream_of(m, "model.asac_seoul.silver_a", None)
    assert next(d for d in ds if d["name"] == "gold_c")["depth"] == 1
    assert len([d for d in ds if d["name"] == "gold_c"]) == 1


def test_seed_traversal_reaches_models():
    m = mini_manifest()
    ds = impact_map.downstream_of(m, "seed.asac_seoul.seed_s", None)
    assert next(d for d in ds if d["name"] == "silver_a")["depth"] == 1
    assert len(ds) == 4


def test_infer_layer():
    assert impact_map.infer_layer("silver_seoul_traffic_incident") == "silver"
    assert impact_map.infer_layer("int_traffic_flow_stats") == "int"
    assert impact_map.infer_layer("gold_weather_forecast_summary") == "gold"
    assert impact_map.infer_layer("dim_admin_dong") == "dim"
    assert impact_map.infer_layer("seed_s") == "other"


def test_summarize():
    m = mini_manifest()
    s = impact_map.summarize(impact_map.downstream_of(m, "model.asac_seoul.silver_a", None))
    assert s == {"total_downstream": 3,
                 "by_layer": {"gold": 2, "int": 1},
                 "by_depth": {"1": 2, "2": 1}}


def test_resolve_simple_name_and_unique_id():
    m = mini_manifest()
    r = impact_map.resolve_targets(m, ["silver_a", "model.asac_seoul.gold_c"])
    assert r[0] == {"query": "silver_a", "found": True, "unique_id": "model.asac_seoul.silver_a"}
    assert r[1]["unique_id"] == "model.asac_seoul.gold_c"


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


def fanout_manifest(n_children):
    """silver_root 하나가 gold_c00..gold_cNN 을 직접 참조하는 팬아웃 픽스처."""
    nodes = {"model.asac_seoul.silver_root": node("silver_root", "silver/silver_root.sql")}
    children = []
    for i in range(n_children):
        name = f"gold_c{i:02d}"
        uid = f"model.asac_seoul.{name}"
        nodes[uid] = node(name, f"gold/{name}.sql")
        children.append(uid)
    return {
        "metadata": {"generated_at": "2099-01-01T00:00:00.000000Z"},
        "nodes": nodes,
        "child_map": {"model.asac_seoul.silver_root": children},
    }


def test_gate_exceeded_over_threshold(tmp_path):
    m = fanout_manifest(11)
    r = impact_map.build_report(m, ["silver_root"], _write_project(tmp_path), None)
    assert r["gate"] == {"threshold": 10, "total_downstream": 11, "exceeded": True}


def test_gate_passes_at_threshold(tmp_path):
    # 게이트 규칙은 초과(>)일 때만 발동 — 정확히 10개면 통과
    m = fanout_manifest(10)
    r = impact_map.build_report(m, ["silver_root"], _write_project(tmp_path), None)
    assert r["gate"] == {"threshold": 10, "total_downstream": 10, "exceeded": False}


def test_gate_unions_shared_downstream(tmp_path):
    # 두 대상이 같은 downstream 을 공유하면 중복 없이 union 으로 센다
    m = mini_manifest()
    r = impact_map.build_report(m, ["silver_a", "int_b"], _write_project(tmp_path), None)
    # silver_a: int_b·gold_d·gold_c / int_b: gold_c → union = int_b·gold_d·gold_c
    assert r["gate"]["total_downstream"] == 3
    assert r["gate"]["exceeded"] is False


def test_gate_custom_threshold(tmp_path):
    m = fanout_manifest(3)
    r = impact_map.build_report(m, ["silver_root"], _write_project(tmp_path), None,
                                threshold=2)
    assert r["gate"] == {"threshold": 2, "total_downstream": 3, "exceeded": True}


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
