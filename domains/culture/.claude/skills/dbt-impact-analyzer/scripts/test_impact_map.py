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
