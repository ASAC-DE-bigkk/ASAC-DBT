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
    nodes = {"model.culture.silver_root": node("silver_root", "silver/silver_root.sql")}
    children = []
    for i in range(n_children):
        name = f"gold_c{i:02d}"
        uid = f"model.culture.{name}"
        nodes[uid] = node(name, f"gold/{name}.sql")
        children.append(uid)
    return {
        "metadata": {"generated_at": "2099-01-01T00:00:00.000000Z"},
        "nodes": nodes,
        "child_map": {"model.culture.silver_root": children},
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


# ── 크로스도메인 스캔 (#129 — manifest 밖 참조) ──────────────────────────────
# 실사고 재현: 남의 도메인이 우리 모델을 source() 로 읽는데 우리 manifest 에는
# 그 참조가 없어 downstream=0 으로 나오던 문제(2026-08-08 culture prod 실패).

def _domains(tmp_path, self_name="culture", others=()):
    """domains/<self>, domains/<other>… 를 만든다. others = [(도메인, 상대경로, 내용)]"""
    root = tmp_path / "domains"
    me = root / self_name
    (me / "models" / "gold").mkdir(parents=True, exist_ok=True)
    (me / "models" / "gold" / "own.sql").write_text("select 1", encoding="utf-8")
    for domain, rel, body in others:
        f = root / domain / "models" / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body, encoding="utf-8")
    return me


def test_cross_domain_finds_source_ref(tmp_path):
    me = _domains(tmp_path, others=[
        ("transit", "gold/g.sql",
         "select *\nfrom {{ source('culture', 'gold_culture_event_schedule') }}\n"),
    ])
    r = impact_map.cross_domain_refs(me, ["gold_culture_event_schedule"])
    assert r["scanned"] is True
    assert r["total"] == 1
    assert r["by_domain"] == {"transit": 1}
    assert r["refs"][0]["line"] == 2
    assert r["refs"][0]["domain"] == "transit"


def test_cross_domain_ignores_source_alias(tmp_path):
    """alias 는 도메인마다 제각각이라 키로 못 쓴다 — 모델명으로 찾는다.

    실측: traffic_weather 는 culture 모델을 `weather_culture_schedule_gold` 라는
    alias 로 읽는다. alias 로 grep 했으면 통째로 놓쳤다.
    """
    me = _domains(tmp_path, others=[
        ("traffic_weather", "weather/g.sql",
         "from {{ source('weather_culture_schedule_gold', 'gold_culture_event_schedule') }}\n"),
    ])
    r = impact_map.cross_domain_refs(me, ["gold_culture_event_schedule"])
    assert r["total"] == 1
    assert r["refs"][0]["domain"] == "traffic_weather"


def test_cross_domain_finds_sources_yml_declaration(tmp_path):
    me = _domains(tmp_path, others=[
        ("citydata", "sources.yml",
         "sources:\n  - name: culture\n    tables:\n      - name: silver_culture_event\n"),
    ])
    r = impact_map.cross_domain_refs(me, ["silver_culture_event"])
    assert r["total"] == 1
    assert r["refs"][0]["file"].endswith("sources.yml")


def test_cross_domain_word_boundary(tmp_path):
    """부분일치 금지 — `gold_x` 가 `gold_x_daily` 에 걸리면 오탐이 쏟아진다."""
    me = _domains(tmp_path, others=[
        ("transit", "gold/g.sql", "from {{ source('c', 'gold_x_daily') }}\n"),
    ])
    assert impact_map.cross_domain_refs(me, ["gold_x"])["total"] == 0
    assert impact_map.cross_domain_refs(me, ["gold_x_daily"])["total"] == 1


def test_cross_domain_skips_build_artifacts(tmp_path):
    """target/ 의 컴파일본은 원본이 아니다 — 세면 같은 참조를 두 번 세거나 선언으로 오독한다."""
    me = _domains(tmp_path, others=[
        ("transit", "gold/g.sql", "from {{ source('culture', 'gold_a') }}\n"),
    ])
    tgt = tmp_path / "domains" / "transit" / "models" / "target" / "compiled.sql"
    tgt.parent.mkdir(parents=True, exist_ok=True)
    tgt.write_text("from culture.gold_a\n", encoding="utf-8")
    assert impact_map.cross_domain_refs(me, ["gold_a"])["total"] == 1


def test_cross_domain_excludes_self(tmp_path):
    """자기 도메인 안의 ref 는 manifest 가 이미 본다 — 여기서 또 세면 중복 보고다."""
    me = _domains(tmp_path, others=[
        ("transit", "gold/g.sql", "select 1\n"),   # 스캔은 실제로 돌되 매치가 없어야 한다
    ])
    (me / "models" / "gold" / "mine.sql").write_text(
        "from {{ ref('gold_a') }}", encoding="utf-8")
    r = impact_map.cross_domain_refs(me, ["gold_a"])
    assert r["scanned"] is True and r["total"] == 0


def test_no_scan_keeps_response_shape(tmp_path):
    """스캔 못 해도 모양이 같아야 한다 — `total` 이 없으면 소비자가 '0건'과 구분 못 한다."""
    me = tmp_path / "solo"
    (me / "models").mkdir(parents=True)
    r = impact_map.cross_domain_refs(me, ["gold_a"], domains_root=tmp_path / "nope")
    assert set(r) == {"scanned", "reason", "scanned_domains", "total", "by_domain", "refs"}
    assert r["total"] == 0


def test_cross_domain_no_root(tmp_path):
    """도메인 루트가 없어도 죽지 않는다 — 스킬이 다른 배치에서도 돈다."""
    me = tmp_path / "solo"
    (me / "models").mkdir(parents=True)
    r = impact_map.cross_domain_refs(me, ["gold_a"], domains_root=tmp_path / "nope")
    assert r["scanned"] is False and r["refs"] == []


def test_report_scans_downstream_names_too(tmp_path):
    """남이 읽는 게 대상 모델이 아니라 그 **하류**일 수 있다(실사고: transit → event_schedule)."""
    m = mini_manifest()
    me = _domains(tmp_path, others=[
        ("transit", "gold/g.sql", "from {{ source('culture', 'gold_c') }}\n"),
    ])
    r = impact_map.build_report(m, ["silver_a"], me, None)
    assert r["cross_domain"]["total"] == 1          # gold_c 는 silver_a 의 depth-2 하류
    assert r["cross_domain"]["refs"][0]["model"] == "gold_c"


def test_report_cross_scan_can_be_disabled(tmp_path):
    m = mini_manifest()
    me = _domains(tmp_path, others=[
        ("transit", "gold/g.sql", "from {{ source('culture', 'gold_c') }}\n"),
    ])
    r = impact_map.build_report(m, ["silver_a"], me, None, scan_cross=False)
    assert r["cross_domain"]["scanned"] is False


# 🔴 응답 모양은 **모든 갈래에서 같다**. 갈래마다 다르면 소비자(SKILL.md 3-1 이 읽는
#    `cross_domain.total`)가 환경에 따라 KeyError 를 맞고, 그건 "참조 0건"과 구분이 안 된다.
#    이 계약이 코드에는 `_no_scan()` 으로 있었는데 build_report 가 손으로 dict 를 만들어
#    우회하고 있었다(2026-08-10) — 그래서 갈래별로 **키 집합을 직접** 못 박는다.
CROSS_KEYS = {"scanned", "reason", "scanned_domains", "total", "by_domain", "refs"}


def _cross(tmp_path, **kw):
    me = _domains(tmp_path, others=[
        ("transit", "gold/g.sql", "from {{ source('culture', 'gold_c') }}\n"),
    ])
    return impact_map.build_report(mini_manifest(), kw.pop("models", ["silver_a"]), me, None, **kw)


def test_cross_shape_is_identical_when_disabled(tmp_path):
    c = _cross(tmp_path, scan_cross=False)["cross_domain"]
    assert CROSS_KEYS <= set(c), f"빠진 키: {CROSS_KEYS - set(c)}"
    assert c["scanned"] is False and c["total"] == 0 and c["by_domain"] == {}
    assert c["reason"] == "--no-cross-scan"


def test_cross_shape_is_identical_when_no_target_resolved(tmp_path):
    c = _cross(tmp_path, models=["존재하지_않는_모델"])["cross_domain"]
    assert CROSS_KEYS <= set(c), f"빠진 키: {CROSS_KEYS - set(c)}"
    assert c["total"] == 0
    # 사유를 갈라 적는다 — 안 찾은 것(플래그)과 못 찾은 것(대상 부재)은 다른 사실이다
    assert "--no-cross-scan" not in c["reason"]


def test_cross_shape_is_identical_when_scanned(tmp_path):
    c = _cross(tmp_path)["cross_domain"]
    assert CROSS_KEYS - {"reason"} <= set(c), f"빠진 키: {CROSS_KEYS - {'reason'} - set(c)}"
    assert c["scanned"] is True
