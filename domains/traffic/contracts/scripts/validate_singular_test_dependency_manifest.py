#!/usr/bin/env python3
"""Validate Traffic singular-test dependencies from a fresh dbt manifest."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence


ROOT_PROJECT_NAME = "asac_seoul"
TRAFFIC_TEST_PREFIX = PurePosixPath("tests/traffic/transform")


class ManifestDependencyError(ValueError):
    """Raised when the Traffic singular-test manifest graph is unsafe."""


def _normalized_path(value: object) -> PurePosixPath | None:
    if not isinstance(value, str):
        return None
    return PurePosixPath(value.replace("\\", "/"))


def _is_traffic_transform_test(path: PurePosixPath | None) -> bool:
    return (
        path is not None
        and path.suffix == ".sql"
        and path.parts[: len(TRAFFIC_TEST_PREFIX.parts)] == TRAFFIC_TEST_PREFIX.parts
    )


def _dependency_node_ids(node: Mapping[object, object]) -> tuple[str, ...]:
    depends_on = node.get("depends_on")
    values = depends_on.get("nodes") if isinstance(depends_on, Mapping) else None
    if not isinstance(values, list):
        return ()
    return tuple(value for value in values if isinstance(value, str))


def validate_manifest(manifest: object) -> None:
    """Validate active Traffic transform singular tests using manifest-native edges."""
    if not isinstance(manifest, Mapping):
        raise ManifestDependencyError(
            "manifest: expected an object with a nodes mapping"
        )

    metadata = manifest.get("metadata")
    project_name = (
        metadata.get("project_name") if isinstance(metadata, Mapping) else None
    )
    if project_name != ROOT_PROJECT_NAME:
        raise ManifestDependencyError(
            "manifest.metadata.project_name: "
            f"expected {ROOT_PROJECT_NAME!r}; actual {project_name!r}"
        )

    nodes = manifest.get("nodes")
    if not isinstance(nodes, Mapping):
        raise ManifestDependencyError("manifest.nodes: expected a mapping")

    scoped: list[tuple[PurePosixPath, Mapping[object, object]]] = []
    for node in nodes.values():
        if not isinstance(node, Mapping) or node.get("resource_type") != "test":
            continue
        path = _normalized_path(node.get("original_file_path"))
        if _is_traffic_transform_test(path):
            assert path is not None
            scoped.append((path, node))

    if not scoped:
        raise ManifestDependencyError(
            "manifest does not contain active singular tests under "
            f"{TRAFFIC_TEST_PREFIX.as_posix()}"
        )

    counts = Counter(path for path, _ in scoped)
    duplicates = sorted(path.as_posix() for path, count in counts.items() if count != 1)
    if duplicates:
        raise ManifestDependencyError(
            f"duplicate Traffic singular-test manifest paths: {duplicates}"
        )

    local_prefix = f"model.{project_name}."
    for path, node in scoped:
        phase = path.parent.name
        expected_tag = f"ask_seoul_traffic_transform_{phase}"
        tags = node.get("tags")
        if not isinstance(tags, list) or expected_tag not in tags:
            raise ManifestDependencyError(
                f"{path.name}: expected phase tag {expected_tag!r} for {phase!r}"
            )

        dependencies = _dependency_node_ids(node)
        if not any(node_id.startswith(local_prefix) for node_id in dependencies):
            raise ManifestDependencyError(
                f"{path.name}: expected at least one local {project_name} model dependency"
            )


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _argument_parser().parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        validate_manifest(manifest)
    except (
        ManifestDependencyError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        print(f"ERROR: {error}")
        return 1

    print("PASS: traffic singular-test dependency manifest is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
