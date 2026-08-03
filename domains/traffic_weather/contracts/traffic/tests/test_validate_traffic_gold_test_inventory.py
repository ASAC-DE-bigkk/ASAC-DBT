from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    PROJECT_ROOT
    / "contracts"
    / "traffic"
    / "scripts"
    / "validate_traffic_gold_test_inventory.py"
)


def _test_node(
    unique_id: str,
    *,
    path: str,
    tags: list[str],
    owner_unique_ids: list[str],
    generic: bool = False,
) -> dict[str, object]:
    node: dict[str, object] = {
        "unique_id": unique_id,
        "resource_type": "test",
        "name": unique_id.rsplit(".", 1)[-1],
        "original_file_path": path,
        "tags": tags,
        "depends_on": {"nodes": owner_unique_ids},
    }
    if generic:
        node["test_metadata"] = {"name": "not_null"}
    return node


def _portfolio_test_nodes() -> dict[str, dict[str, object]]:
    nodes: dict[str, dict[str, object]] = {}

    def add_group(
        prefix: str,
        count: int,
        tag: str | None,
        owner_unique_id: str,
        *,
        generic: bool = False,
    ) -> None:
        for index in range(1, count + 1):
            unique_id = f"test.asac_seoul.{prefix}_{index:03d}"
            owners = [owner_unique_id]
            if prefix == "gold_gate" and index == 1:
                owners.append("model.asac_seoul.silver_seoul_traffic_incident")
            nodes[unique_id] = _test_node(
                unique_id,
                path=f"tests/traffic/transform/{prefix}/{prefix}_{index:03d}.sql",
                tags=[] if tag is None else [tag],
                owner_unique_ids=owners,
                generic=generic and index != 1,
            )

    add_group(
        "availability",
        1,
        "ask_seoul_traffic_transform_availability",
        "model.asac_seoul.gold_traffic_incident_summary",
    )
    add_group(
        "bronze_source",
        70,
        None,
        "source.asac_seoul.traffic_bronze.incident",
    )
    add_group(
        "silver",
        43,
        "ask_seoul_traffic_transform_silver",
        "model.asac_seoul.silver_seoul_traffic_incident",
    )
    add_group(
        "gold_gate",
        163,
        "traffic_gold_gate",
        "model.asac_seoul.gold_traffic_incident_summary",
        generic=True,
    )
    add_group(
        "gold_hourly",
        20,
        "traffic_gold_hourly_extension",
        "model.asac_seoul.gold_traffic_incident_summary",
        generic=True,
    )
    add_group(
        "gold_daily",
        30,
        "traffic_gold_daily_extension",
        "model.asac_seoul.gold_traffic_incident_summary",
        generic=True,
    )

    for index in range(1, 8):
        unique_id = f"test.asac_axes.axes_static_{index:03d}"
        nodes[unique_id] = _test_node(
            unique_id,
            path=f"tests/asac_axes/axes_static_{index:03d}.sql",
            tags=[],
            owner_unique_ids=["seed.asac_axes.asac_axes_calendar"],
        )
    for index in range(1, 4):
        unique_id = f"test.asac_seoul.admin_static_{index:03d}"
        nodes[unique_id] = _test_node(
            unique_id,
            path=f"tests/common_admin/admin_static_{index:03d}.sql",
            tags=[],
            owner_unique_ids=["seed.asac_seoul.common_admin_dong"],
        )
    nodes["seed.asac_axes.asac_axes_calendar"] = {
        "unique_id": "seed.asac_axes.asac_axes_calendar",
        "resource_type": "seed",
        "tags": ["ask_seoul_traffic_transform_asac_axes_contract"],
    }
    nodes["seed.asac_seoul.common_admin_dong"] = {
        "unique_id": "seed.asac_seoul.common_admin_dong",
        "resource_type": "seed",
        "tags": ["ask_seoul_traffic_transform_common_admin"],
    }
    return nodes


def _manifest() -> dict[str, object]:
    return {
        "metadata": {"project_name": "asac_seoul"},
        "nodes": _portfolio_test_nodes(),
        "sources": {
            "source.asac_seoul.traffic_bronze.incident": {
                "unique_id": "source.asac_seoul.traffic_bronze.incident",
                "resource_type": "source",
                "tags": ["ask_seoul_traffic_transform_source"],
            }
        },
    }


def _inventory() -> dict[str, object]:
    manifest = _manifest()
    tests = []
    tier_by_tag = {
        "traffic_gold_gate": "gate",
        "traffic_gold_hourly_extension": "hourly_extension",
        "traffic_gold_daily_extension": "daily_extension",
        "ask_seoul_traffic_transform_asac_axes_contract": "full_static",
        "ask_seoul_traffic_transform_common_admin": "full_static",
    }
    nodes = manifest["nodes"]
    assert isinstance(nodes, dict)
    for unique_id, node in sorted(nodes.items()):
        if node.get("resource_type") != "test":
            continue
        tags = set(node["tags"])
        tier_tag = next((tag for tag in tier_by_tag if tag in tags), None)
        depends_on = node["depends_on"]
        assert isinstance(depends_on, dict)
        if tier_tag is None:
            owner_tags = {
                tag
                for owner_unique_id in depends_on["nodes"]
                if owner_unique_id in nodes
                for tag in nodes[owner_unique_id]["tags"]
            }
            tier_tag = next(
                (tag for tag in tier_by_tag if tag in owner_tags),
                None,
            )
        if tier_tag is None:
            continue
        tests.append(
            {
                "unique_id": unique_id,
                "path": node["original_file_path"],
                "test_type": "generic" if "test_metadata" in node else "singular",
                "owner_unique_ids": sorted(depends_on["nodes"]),
                "tier": tier_by_tag[tier_tag],
                "tier_tag": tier_tag,
            }
        )
    return {
        "version": 1,
        "tiers": {
            "gate": {"expected_count": 163},
            "hourly_extension": {"expected_count": 20},
            "daily_extension": {"expected_count": 30},
            "full_static": {"expected_count": 10},
        },
        "total_expected": {
            "gold_gate": 163,
            "gold_hourly": 183,
            "gold_full": 213,
            "traffic_gate": 277,
            "traffic_hourly": 297,
            "traffic_full": 337,
        },
        "tests": tests,
    }


def _entry(inventory: dict[str, object], unique_id: str) -> dict[str, object]:
    tests = inventory["tests"]
    assert isinstance(tests, list)
    return next(item for item in tests if item["unique_id"] == unique_id)


@pytest.fixture
def validator():
    from contracts.traffic.scripts import (
        validate_traffic_gold_test_inventory as module,
    )

    return module


def test_valid_inventory_matches_manifest(validator) -> None:
    validator.validate_inventory(
        _manifest(),
        _inventory(),
        selector_counts=validator.EXPECTED_SELECTOR_COUNTS,
    )


def test_missing_manifest_test_fails(validator) -> None:
    manifest = _manifest()
    del manifest["nodes"]["test.asac_seoul.gold_daily_001"]

    with pytest.raises(validator.InventoryError, match="missing.*gold_daily_001"):
        validator.validate_inventory(manifest, _inventory())


def test_extra_manifest_test_fails(validator) -> None:
    manifest = _manifest()
    manifest["nodes"]["test.asac_seoul.unclassified"] = _test_node(
        "test.asac_seoul.unclassified",
        path="tests/traffic/transform/gold/unclassified.sql",
        tags=["traffic_gold_gate"],
        owner_unique_ids=["model.asac_seoul.gold_traffic_incident_summary"],
    )

    with pytest.raises(validator.InventoryError, match="extra.*unclassified"):
        validator.validate_inventory(manifest, _inventory())


@pytest.mark.parametrize(
    "tags",
    ([], ["ask_seoul_traffic_transform_gold"]),
)
def test_untiered_traffic_gold_test_fails(validator, tags: list[str]) -> None:
    manifest = _manifest()
    manifest["nodes"]["test.asac_seoul.untiered_gold"] = _test_node(
        "test.asac_seoul.untiered_gold",
        path="tests/traffic/transform/gold/untiered_gold.sql",
        tags=tags,
        owner_unique_ids=["model.asac_seoul.gold_traffic_incident_summary"],
    )

    with pytest.raises(validator.InventoryError, match="untiered_gold.*tier"):
        validator.validate_inventory(manifest, _inventory())


def test_duplicate_inventory_unique_id_fails(validator) -> None:
    inventory = _inventory()
    inventory["tests"].append(dict(inventory["tests"][0]))

    with pytest.raises(validator.InventoryError, match="duplicate"):
        validator.validate_inventory(_manifest(), inventory)


def test_unsupported_inventory_version_fails(validator) -> None:
    inventory = _inventory()
    inventory["version"] = 2

    with pytest.raises(validator.InventoryError, match="version"):
        validator.validate_inventory(_manifest(), inventory)


@pytest.mark.parametrize("field", ["path", "test_type", "tier", "tier_tag"])
def test_inventory_record_field_mismatch_fails(validator, field: str) -> None:
    inventory = _inventory()
    _entry(inventory, "test.asac_seoul.gold_gate_001")[field] = "wrong"

    with pytest.raises(validator.InventoryError, match=field):
        validator.validate_inventory(_manifest(), inventory)


def test_owner_unique_ids_preserve_all_manifest_owners_in_sorted_order(validator) -> None:
    inventory = _inventory()
    entry = _entry(inventory, "test.asac_seoul.gold_gate_001")
    assert len(entry["owner_unique_ids"]) == 2
    entry["owner_unique_ids"] = list(reversed(entry["owner_unique_ids"]))

    with pytest.raises(validator.InventoryError, match="owner_unique_ids"):
        validator.validate_inventory(_manifest(), inventory)


def test_empty_owner_unique_ids_fails(validator) -> None:
    inventory = _inventory()
    _entry(inventory, "test.asac_seoul.gold_gate_001")["owner_unique_ids"] = []

    with pytest.raises(validator.InventoryError, match="non-empty"):
        validator.validate_inventory(_manifest(), inventory)


def test_tier_count_mismatch_fails(validator) -> None:
    inventory = _inventory()
    inventory["tiers"]["gate"]["expected_count"] = 122

    with pytest.raises(validator.InventoryError, match="tier gate"):
        validator.validate_inventory(_manifest(), inventory)


def test_portfolio_count_mismatch_fails(validator) -> None:
    manifest = _manifest()
    manifest["nodes"]["test.asac_seoul.availability_001"]["tags"] = []

    with pytest.raises(validator.InventoryError, match="portfolio counts"):
        validator.validate_inventory(manifest, _inventory())


def test_test_cannot_belong_to_multiple_portfolio_groups(validator) -> None:
    manifest = _manifest()
    manifest["nodes"]["test.asac_seoul.availability_001"]["tags"].append(
        "ask_seoul_traffic_transform_source"
    )

    with pytest.raises(validator.InventoryError, match="multiple portfolio groups"):
        validator.validate_inventory(manifest, _inventory())


@pytest.mark.parametrize(
    "bad_key,bad_value",
    ((42, {}), ("test.asac_seoul.malformed", "not-a-node")),
)
def test_malformed_manifest_node_fails(
    validator,
    bad_key: object,
    bad_value: object,
) -> None:
    manifest = _manifest()
    manifest["nodes"][bad_key] = bad_value

    with pytest.raises(validator.InventoryError, match="manifest.nodes"):
        validator.validate_inventory(manifest, _inventory())


def test_cadence_total_mismatch_fails(validator) -> None:
    inventory = _inventory()
    inventory["total_expected"]["traffic_full"] = 296

    with pytest.raises(validator.InventoryError, match=r"total_expected\.traffic_full"):
        validator.validate_inventory(_manifest(), inventory)


def test_selector_count_mismatch_fails(validator) -> None:
    with pytest.raises(validator.InventoryError, match="selector counts"):
        validator.validate_inventory(
            _manifest(),
            _inventory(),
            selector_counts={
                **validator.EXPECTED_SELECTOR_COUNTS,
                "ask_seoul_traffic_transform_gold_full_tests": 172,
            },
        )


def test_generate_candidate_preserves_multiple_owners(validator) -> None:
    candidate = validator.generate_candidate(_manifest())
    entry = _entry(candidate, "test.asac_seoul.gold_gate_001")

    assert entry["owner_unique_ids"] == [
        "model.asac_seoul.gold_traffic_incident_summary",
        "model.asac_seoul.silver_seoul_traffic_incident",
    ]


def test_gold_tier_wins_when_gold_test_depends_on_static_owner(validator) -> None:
    manifest = _manifest()
    node = manifest["nodes"]["test.asac_seoul.gold_gate_001"]
    node["depends_on"]["nodes"].append("seed.asac_seoul.common_admin_dong")

    candidate = validator.generate_candidate(manifest)
    entry = _entry(candidate, "test.asac_seoul.gold_gate_001")

    assert entry["tier"] == "gate"
    assert entry["tier_tag"] == "traffic_gold_gate"


def test_static_tier_requires_all_parents_to_match_cautious_selector(
    validator,
) -> None:
    manifest = _manifest()
    manifest["nodes"]["model.asac_seoul.weather"] = {
        "unique_id": "model.asac_seoul.weather",
        "resource_type": "model",
        "tags": [],
    }
    manifest["nodes"]["test.asac_seoul.weather_with_admin"] = _test_node(
        "test.asac_seoul.weather_with_admin",
        path="tests/weather/weather_with_admin.sql",
        tags=[],
        owner_unique_ids=[
            "seed.asac_seoul.common_admin_dong",
            "model.asac_seoul.weather",
        ],
    )

    candidate = validator.generate_candidate(manifest)
    candidate_ids = {record["unique_id"] for record in candidate["tests"]}

    assert "test.asac_seoul.weather_with_admin" not in candidate_ids


def test_candidate_contains_manifest_identity_and_contract_fields(validator) -> None:
    candidate = validator.generate_candidate(_manifest())
    record = candidate["tests"][0]

    assert set(record) == {
        "unique_id",
        "path",
        "test_type",
        "owner_unique_ids",
        "tier",
        "tier_tag",
    }
    assert candidate["portfolio_expected"] == {
        "availability": 1,
        "bronze_source": 70,
        "silver": 43,
        "gold_gate": 163,
        "gold_hourly_extension": 20,
        "gold_daily_extension": 30,
        "full_static": 10,
    }


def test_generate_candidate_rejects_test_without_model_or_seed_owner(validator) -> None:
    manifest = _manifest()
    manifest["nodes"]["test.asac_seoul.gold_gate_001"]["depends_on"] = {
        "nodes": ["source.asac_seoul.traffic_bronze.incident"]
    }

    with pytest.raises(validator.InventoryError, match="at least one.*owner"):
        validator.generate_candidate(manifest)


def test_generate_candidate_rejects_manifest_count_drift(validator) -> None:
    manifest = _manifest()
    del manifest["nodes"]["test.asac_seoul.gold_daily_001"]

    with pytest.raises(validator.InventoryError, match="candidate tier counts"):
        validator.generate_candidate(manifest)


@pytest.mark.parametrize(
    "value",
    ("missing-separator", "=123", "selector=not-an-int", "selector=-1"),
)
def test_invalid_selector_count_fails(validator, value: str) -> None:
    with pytest.raises(validator.InventoryError, match="invalid selector count"):
        validator.parse_selector_counts([value])


def test_cli_reports_pass(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    inventory_path = tmp_path / "inventory.yml"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    inventory_path.write_text(
        yaml.safe_dump(_inventory(), sort_keys=False), encoding="utf-8"
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest_path),
            "--inventory",
            str(inventory_path),
            "--selector-count",
            "ask_seoul_traffic_transform_gold_gate_tests=163",
            "--selector-count",
            "ask_seoul_traffic_transform_gold_hourly_tests=183",
            "--selector-count",
            "ask_seoul_traffic_transform_gold_full_tests=213",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout
    assert "PASS" in result.stdout
    assert result.stderr == ""


def test_cli_rejects_duplicate_inventory_yaml_key(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    inventory_path = tmp_path / "inventory.yml"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    inventory_text = yaml.safe_dump(_inventory(), sort_keys=False).replace(
        "version: 1\n",
        "version: 1\nversion: 1\n",
        1,
    )
    inventory_path.write_text(inventory_text, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest_path),
            "--inventory",
            str(inventory_path),
        ],
        cwd=PROJECT_ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "duplicate YAML key" in result.stdout
    assert result.stderr == ""
