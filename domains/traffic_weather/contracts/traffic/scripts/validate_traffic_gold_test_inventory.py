#!/usr/bin/env python3
"""Validate Traffic Gold test cadence inventory against a fresh dbt manifest."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Mapping, Sequence

import yaml
from yaml.resolver import BaseResolver


INVENTORY_VERSION = 1
VALID_TIERS = ("gate", "hourly_extension", "daily_extension", "full_static")
GOLD_TIER_TAGS = {
    "gate": "traffic_gold_gate",
    "hourly_extension": "traffic_gold_hourly_extension",
    "daily_extension": "traffic_gold_daily_extension",
}
SELECTOR_TIERS = {
    "ask_seoul_traffic_transform_gold_gate_tests": ("gate",),
    "ask_seoul_traffic_transform_gold_hourly_tests": (
        "gate",
        "hourly_extension",
    ),
    "ask_seoul_traffic_transform_gold_full_tests": (
        "gate",
        "hourly_extension",
        "daily_extension",
    ),
}
STATIC_TIER_TAGS = {
    "ask_seoul_traffic_transform_asac_axes_contract",
    "ask_seoul_traffic_transform_common_admin",
}
EXPECTED_STATIC_TAG_COUNTS = {
    "ask_seoul_traffic_transform_asac_axes_contract": 7,
    "ask_seoul_traffic_transform_common_admin": 3,
}
PORTFOLIO_GROUP_TAGS = {
    "availability": {"ask_seoul_traffic_transform_availability"},
    "bronze_source": {"ask_seoul_traffic_transform_source"},
    "silver": {"ask_seoul_traffic_transform_silver"},
    "gold_gate": {"traffic_gold_gate"},
    "gold_hourly_extension": {"traffic_gold_hourly_extension"},
    "gold_daily_extension": {"traffic_gold_daily_extension"},
    "full_static": STATIC_TIER_TAGS,
}
EXPECTED_PORTFOLIO_COUNTS = {
    "availability": 1,
    "bronze_source": 121,
    "silver": 76,
    "gold_gate": 162,
    "gold_hourly_extension": 20,
    "gold_daily_extension": 30,
    "full_static": 10,
}
EXPECTED_SELECTOR_COUNTS = {
    "ask_seoul_traffic_transform_gold_gate_tests": 162,
    "ask_seoul_traffic_transform_gold_hourly_tests": 182,
    "ask_seoul_traffic_transform_gold_full_tests": 212,
}
EXPECTED_CADENCE_COUNTS = {
    "traffic_gate": 360,
    "traffic_hourly": 380,
    "traffic_full": 420,
}
EXPECTED_TIER_COUNTS = {
    "gate": 162,
    "hourly_extension": 20,
    "daily_extension": 30,
    "full_static": 10,
}
TRAFFIC_GOLD_TAG = "ask_seoul_traffic_transform_gold"
TRAFFIC_GOLD_SINGULAR_PATH_PREFIX = "tests/traffic/transform/gold/"


class InventoryError(ValueError):
    """Raised when the Traffic Gold cadence inventory is not exact."""


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects last-key-wins inventory ambiguity."""


def _construct_unique_mapping(
    loader: _UniqueKeyLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    loader.flatten_mapping(node)
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as error:
            raise InventoryError(f"unhashable YAML mapping key: {key!r}") from error
        if duplicate:
            raise InventoryError(f"duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _mapping(value: object, label: str) -> Mapping[object, object]:
    if not isinstance(value, Mapping):
        raise InventoryError(f"{label}: expected mapping")
    return value


def _manifest_nodes(
    manifest: Mapping[object, object],
) -> dict[str, Mapping[object, object]]:
    raw_nodes = _mapping(manifest.get("nodes"), "manifest.nodes")
    nodes: dict[str, Mapping[object, object]] = {}
    for unique_id, node in raw_nodes.items():
        if not isinstance(unique_id, str) or not unique_id:
            raise InventoryError(
                f"manifest.nodes: expected non-empty string key, got {unique_id!r}"
            )
        if not isinstance(node, Mapping):
            raise InventoryError(f"manifest.nodes.{unique_id}: expected mapping")
        nodes[unique_id] = node
    return nodes


def _manifest_resources(
    manifest: Mapping[object, object],
) -> dict[str, Mapping[object, object]]:
    resources = _manifest_nodes(manifest)
    raw_sources = _mapping(manifest.get("sources", {}), "manifest.sources")
    for unique_id, source in raw_sources.items():
        if not isinstance(unique_id, str) or not unique_id:
            raise InventoryError(
                f"manifest.sources: expected non-empty string key, got {unique_id!r}"
            )
        if unique_id in resources:
            raise InventoryError(f"duplicate manifest resource unique id: {unique_id}")
        if not isinstance(source, Mapping):
            raise InventoryError(f"manifest.sources.{unique_id}: expected mapping")
        resources[unique_id] = source
    return resources


def _inventory_entries(
    inventory: Mapping[object, object],
) -> list[Mapping[object, object]]:
    tests = inventory.get("tests")
    if not isinstance(tests, list) or not tests:
        raise InventoryError("inventory tests: expected non-empty list")
    return [_mapping(item, "inventory test entry") for item in tests]


def _node_tags(node: Mapping[object, object], unique_id: str) -> set[str]:
    tags = node.get("tags")
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        raise InventoryError(f"{unique_id}: tags must be a string list")
    return set(tags)


def manifest_selector_counts(manifest: object) -> dict[str, int]:
    """Return exact Traffic Gold cadence selector counts from manifest tags."""
    nodes = _manifest_nodes(_mapping(manifest, "manifest"))
    tier_node_ids = {tier: set() for tier in GOLD_TIER_TAGS}
    for unique_id, node in nodes.items():
        if node.get("resource_type") != "test":
            continue
        tags = _node_tags(node, unique_id)
        if TRAFFIC_GOLD_TAG not in tags:
            continue
        for tier, tier_tag in GOLD_TIER_TAGS.items():
            if tier_tag in tags:
                tier_node_ids[tier].add(unique_id)

    return {
        selector: len(
            set().union(*(tier_node_ids[tier] for tier in tiers))
        )
        for selector, tiers in SELECTOR_TIERS.items()
    }


def _owner_unique_ids(node: Mapping[object, object], unique_id: str) -> list[str]:
    depends_on = _mapping(node.get("depends_on"), f"{unique_id}.depends_on")
    dependencies = depends_on.get("nodes")
    if not isinstance(dependencies, list):
        raise InventoryError(f"{unique_id}.depends_on.nodes: expected list")
    owners = [
        dependency
        for dependency in dependencies
        if isinstance(dependency, str)
        and dependency.startswith(("model.", "seed."))
    ]
    if len(owners) != len(set(owners)):
        raise InventoryError(f"{unique_id}: duplicate model/seed owner unique ids")
    return sorted(owners)


def _tier_from_tags(unique_id: str, tags: set[str]) -> tuple[str, str] | None:
    matching = [
        (tier, tag) for tier, tag in GOLD_TIER_TAGS.items() if tag in tags
    ]
    matching.extend(("full_static", tag) for tag in sorted(tags & STATIC_TIER_TAGS))
    if len(matching) > 1:
        raise InventoryError(f"{unique_id}: test belongs to multiple minimum tiers")
    return matching[0] if matching else None


def _cautious_parent_tags(
    unique_id: str,
    node: Mapping[object, object],
    resources: Mapping[str, Mapping[object, object]],
    candidate_tags: set[str],
) -> set[str]:
    """Return selector tags shared by every dependency under cautious selection."""
    depends_on = _mapping(node.get("depends_on"), f"{unique_id}.depends_on")
    dependencies = depends_on.get("nodes")
    if not isinstance(dependencies, list):
        raise InventoryError(f"{unique_id}.depends_on.nodes: expected list")
    if any(
        not isinstance(dependency, str) or not dependency
        for dependency in dependencies
    ):
        raise InventoryError(
            f"{unique_id}.depends_on.nodes: expected non-empty string entries"
        )
    if not dependencies:
        return set()

    return {
        candidate_tag
        for candidate_tag in candidate_tags
        if all(
            dependency in resources
            and candidate_tag
            in _node_tags(resources[dependency], dependency)
            for dependency in dependencies
        )
    }


def _cautious_static_tier_from_parents(
    unique_id: str,
    node: Mapping[object, object],
    resources: Mapping[str, Mapping[object, object]],
) -> tuple[str, str] | None:
    """Resolve static tests selected indirectly from fully selected parents."""
    matching_tags = sorted(
        _cautious_parent_tags(
            unique_id,
            node,
            resources,
            STATIC_TIER_TAGS,
        )
    )
    if len(matching_tags) > 1:
        raise InventoryError(
            f"{unique_id}: test belongs to multiple indirect static tiers"
        )
    if not matching_tags:
        return None
    return "full_static", matching_tags[0]


def _manifest_test_records(
    manifest: Mapping[object, object],
) -> dict[str, dict[str, object]]:
    nodes = _manifest_nodes(manifest)
    resources = _manifest_resources(manifest)
    selected: dict[str, dict[str, object]] = {}
    for unique_id, node_value in nodes.items():
        if node_value.get("resource_type") != "test":
            continue
        tags = _node_tags(node_value, unique_id)
        path = node_value.get("original_file_path")
        if not isinstance(path, str) or not path:
            raise InventoryError(f"{unique_id}: original_file_path must be non-empty")
        normalized_path = path.replace("\\", "/")
        tier = _tier_from_tags(unique_id, tags)
        is_traffic_gold = (
            TRAFFIC_GOLD_TAG in tags
            or normalized_path.startswith(TRAFFIC_GOLD_SINGULAR_PATH_PREFIX)
        )
        if tier is None:
            if is_traffic_gold:
                raise InventoryError(
                    f"{unique_id}: Traffic Gold test is missing a cadence tier tag"
                )
            tier = _cautious_static_tier_from_parents(
                unique_id,
                node_value,
                resources,
            )
            if tier is None:
                continue
        if is_traffic_gold and tier[0] == "full_static":
            raise InventoryError(
                f"{unique_id}: Traffic Gold test requires a Gold cadence tier tag"
            )
        selected[unique_id] = {
            "unique_id": unique_id,
            "path": normalized_path,
            "test_type": (
                "generic"
                if isinstance(node_value.get("test_metadata"), Mapping)
                else "singular"
            ),
            "owner_unique_ids": _owner_unique_ids(node_value, unique_id),
            "tier": tier[0],
            "tier_tag": tier[1],
        }
    return selected


def _validate_inventory_entry(entry: Mapping[object, object]) -> tuple[str, str]:
    unique_id = entry.get("unique_id")
    if not isinstance(unique_id, str) or not unique_id:
        raise InventoryError("inventory test entry unique_id: expected non-empty string")
    tier = entry.get("tier")
    if tier not in VALID_TIERS:
        raise InventoryError(f"{unique_id}: invalid tier {tier!r}")
    path = entry.get("path")
    if not isinstance(path, str) or not path:
        raise InventoryError(f"{unique_id}: path must be a non-empty string")
    test_type = entry.get("test_type")
    if test_type not in {"generic", "singular"}:
        raise InventoryError(f"{unique_id}: invalid test_type {test_type!r}")
    tier_tag = entry.get("tier_tag")
    if not isinstance(tier_tag, str) or not tier_tag:
        raise InventoryError(f"{unique_id}: tier_tag must be a non-empty string")
    owner_unique_ids = entry.get("owner_unique_ids")
    if (
        not isinstance(owner_unique_ids, list)
        or not owner_unique_ids
        or any(not isinstance(owner, str) or not owner for owner in owner_unique_ids)
    ):
        raise InventoryError(
            f"{unique_id}: owner_unique_ids must be a non-empty string list"
        )
    if owner_unique_ids != sorted(set(owner_unique_ids)):
        raise InventoryError(
            f"{unique_id}: owner_unique_ids must be unique and sorted"
        )
    return unique_id, str(tier)


def _manifest_portfolio_counts(
    manifest: Mapping[object, object],
) -> tuple[Counter[str], Counter[str]]:
    nodes = _manifest_nodes(manifest)
    resources = _manifest_resources(manifest)
    group_counts: Counter[str] = Counter()
    static_tag_counts: Counter[str] = Counter()
    for unique_id, node_value in nodes.items():
        if node_value.get("resource_type") != "test":
            continue
        tags = _node_tags(node_value, unique_id)
        matching_groups = [
            group
            for group, required_tags in PORTFOLIO_GROUP_TAGS.items()
            if tags & required_tags
        ]
        selected_group_tag: str | None = None
        if not matching_groups:
            candidate_tags = set().union(*PORTFOLIO_GROUP_TAGS.values())
            inherited_tags = _cautious_parent_tags(
                unique_id,
                node_value,
                resources,
                candidate_tags,
            )
            indirect_matches = [
                (group, tag)
                for group, required_tags in PORTFOLIO_GROUP_TAGS.items()
                for tag in sorted(required_tags & inherited_tags)
            ]
            if len(indirect_matches) > 1:
                raise InventoryError(
                    f"{unique_id}: test belongs to multiple indirect portfolio "
                    f"selectors {indirect_matches}"
                )
            if indirect_matches:
                matching_groups = [indirect_matches[0][0]]
                selected_group_tag = indirect_matches[0][1]
        if len(matching_groups) > 1:
            raise InventoryError(
                f"{unique_id}: test belongs to multiple portfolio groups "
                f"{matching_groups}"
            )
        if matching_groups:
            group = matching_groups[0]
            group_counts[group] += 1
            if group == "full_static":
                if selected_group_tag is None:
                    direct_static_tags = sorted(tags & STATIC_TIER_TAGS)
                    if len(direct_static_tags) == 1:
                        selected_group_tag = direct_static_tags[0]
                if selected_group_tag is None:
                    raise InventoryError(
                        f"{unique_id}: full_static group requires one static tier tag"
                    )
                static_tag_counts[selected_group_tag] += 1
    return group_counts, static_tag_counts


def _validate_manifest_portfolio(manifest: Mapping[object, object]) -> None:
    group_counts, static_tag_counts = _manifest_portfolio_counts(manifest)
    actual_portfolio_counts = {
        group: group_counts[group] for group in EXPECTED_PORTFOLIO_COUNTS
    }
    if actual_portfolio_counts != EXPECTED_PORTFOLIO_COUNTS:
        raise InventoryError(
            "manifest portfolio counts mismatch: "
            f"expected {EXPECTED_PORTFOLIO_COUNTS}, "
            f"actual {actual_portfolio_counts}"
        )
    actual_static_counts = {
        tag: static_tag_counts[tag] for tag in EXPECTED_STATIC_TAG_COUNTS
    }
    if actual_static_counts != EXPECTED_STATIC_TAG_COUNTS:
        raise InventoryError(
            "manifest static axes/admin counts mismatch: "
            f"expected {EXPECTED_STATIC_TAG_COUNTS}, "
            f"actual {actual_static_counts}"
        )

    cadence_counts = {
        "traffic_gate": (
            group_counts["availability"]
            + group_counts["bronze_source"]
            + group_counts["silver"]
            + group_counts["gold_gate"]
        ),
        "traffic_hourly": (
            group_counts["availability"]
            + group_counts["bronze_source"]
            + group_counts["silver"]
            + group_counts["gold_gate"]
            + group_counts["gold_hourly_extension"]
        ),
        "traffic_full": sum(
            group_counts[group] for group in PORTFOLIO_GROUP_TAGS
        ),
    }
    if cadence_counts != EXPECTED_CADENCE_COUNTS:
        raise InventoryError(f"manifest cadence counts mismatch: {cadence_counts}")


def validate_inventory(
    manifest: object,
    inventory: object,
) -> None:
    """Validate a tracked inventory against manifest-native test records."""
    manifest_doc = _mapping(manifest, "manifest")
    inventory_doc = _mapping(inventory, "inventory")
    version = inventory_doc.get("version")
    if type(version) is not int or version != INVENTORY_VERSION:
        raise InventoryError(
            f"inventory.version: expected {INVENTORY_VERSION}, got {version!r}"
        )
    entries = _inventory_entries(inventory_doc)

    ids: list[str] = []
    tiers: Counter[str] = Counter()
    for entry in entries:
        unique_id, tier = _validate_inventory_entry(entry)
        ids.append(unique_id)
        tiers[tier] += 1

    duplicates = sorted(
        unique_id for unique_id, count in Counter(ids).items() if count != 1
    )
    if duplicates:
        raise InventoryError(f"duplicate inventory unique_id values: {duplicates}")

    tier_config = _mapping(inventory_doc.get("tiers"), "inventory.tiers")
    for tier in VALID_TIERS:
        config = _mapping(tier_config.get(tier), f"inventory.tiers.{tier}")
        expected_count = config.get("expected_count")
        if tiers[tier] != expected_count:
            raise InventoryError(
                f"tier {tier}: expected_count {expected_count!r}, "
                f"actual inventory count {tiers[tier]}"
            )

    actual_records = _manifest_test_records(manifest_doc)
    expected_ids = set(ids)
    actual_ids = set(actual_records)
    missing = sorted(expected_ids - actual_ids)
    extra = sorted(actual_ids - expected_ids)
    if missing:
        raise InventoryError(
            f"missing manifest tests from inventory comparison: {missing}"
        )
    if extra:
        raise InventoryError(
            f"extra manifest tests not classified by inventory: {extra}"
        )

    for entry in entries:
        unique_id = str(entry["unique_id"])
        actual = actual_records[unique_id]
        for field in (
            "path",
            "test_type",
            "owner_unique_ids",
            "tier",
            "tier_tag",
        ):
            if entry.get(field) != actual[field]:
                raise InventoryError(f"{unique_id}: {field} mismatch")

    total_expected = _mapping(
        inventory_doc.get("total_expected"), "inventory.total_expected"
    )
    required_totals = {
        "gold_gate": tiers["gate"],
        "gold_hourly": tiers["gate"] + tiers["hourly_extension"],
        "gold_full": (
            tiers["gate"]
            + tiers["hourly_extension"]
            + tiers["daily_extension"]
        ),
        **EXPECTED_CADENCE_COUNTS,
    }
    for key, expected in required_totals.items():
        if total_expected.get(key) != expected:
            raise InventoryError(
                f"total_expected.{key}: expected {expected}, "
                f"actual {total_expected.get(key)!r}"
            )

    _validate_manifest_portfolio(manifest_doc)

    actual_selector_counts = manifest_selector_counts(manifest_doc)
    if actual_selector_counts != EXPECTED_SELECTOR_COUNTS:
        raise InventoryError(
            "selector counts mismatch: "
            f"expected {EXPECTED_SELECTOR_COUNTS}, actual {actual_selector_counts}"
        )


def generate_candidate(manifest: object) -> dict[str, object]:
    """Generate sorted inventory candidate records from a fresh manifest."""
    manifest_doc = _mapping(manifest, "manifest")
    records = _manifest_test_records(manifest_doc)
    actual_tier_counts = Counter(
        str(record["tier"]) for record in records.values()
    )
    normalized_tier_counts = {
        tier: actual_tier_counts[tier] for tier in VALID_TIERS
    }
    if normalized_tier_counts != EXPECTED_TIER_COUNTS:
        raise InventoryError(
            "candidate tier counts mismatch: "
            f"expected {EXPECTED_TIER_COUNTS}, actual {normalized_tier_counts}"
        )
    _validate_manifest_portfolio(manifest_doc)
    tests = []
    for unique_id in sorted(records):
        record = records[unique_id]
        owners = record["owner_unique_ids"]
        if not owners:
            raise InventoryError(
                f"{unique_id}: expected at least one model/seed owner unique id"
            )
        tests.append(dict(record))
    return {
        "version": INVENTORY_VERSION,
        "tiers": {
            tier: {"expected_count": count}
            for tier, count in EXPECTED_TIER_COUNTS.items()
        },
        "total_expected": {
            "gold_gate": 162,
            "gold_hourly": 182,
            "gold_full": 212,
            **EXPECTED_CADENCE_COUNTS,
        },
        "portfolio_expected": EXPECTED_PORTFOLIO_COUNTS,
        "selector_expected": EXPECTED_SELECTOR_COUNTS,
        "cadence_expected": EXPECTED_CADENCE_COUNTS,
        "tests": tests,
    }


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inventory", type=Path)
    mode.add_argument("--generate-candidate", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _argument_parser().parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        if args.generate_candidate is not None:
            candidate = generate_candidate(manifest)
            args.generate_candidate.write_text(
                yaml.safe_dump(candidate, sort_keys=False), encoding="utf-8"
            )
            print(
                f"PASS: generated {len(candidate['tests'])} candidate records "
                f"({EXPECTED_TIER_COUNTS['gate']}/{EXPECTED_TIER_COUNTS['hourly_extension']}/"
                f"{EXPECTED_TIER_COUNTS['daily_extension']}/{EXPECTED_TIER_COUNTS['full_static']})"
            )
            return 0
        inventory = yaml.load(
            args.inventory.read_text(encoding="utf-8"),
            Loader=_UniqueKeyLoader,
        )
        validate_inventory(manifest, inventory)
    except (
        InventoryError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        yaml.YAMLError,
    ) as error:
        print(f"ERROR: {error}")
        return 1
    print(
        "PASS: traffic Gold test cadence inventory is valid "
        f"({EXPECTED_CADENCE_COUNTS['traffic_gate']}/"
        f"{EXPECTED_CADENCE_COUNTS['traffic_hourly']}/"
        f"{EXPECTED_CADENCE_COUNTS['traffic_full']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
