"""Internal _manifest_contract service responsibility."""

from __future__ import annotations

from typing import Iterable, Mapping

from .foundation import (
    ArtifactShapeError,
    CATALOG_SCHEMA_VERSION,
    MANIFEST_V12_SUFFIX,
    PUBLIC_VISIBILITIES,
    _error,
    _preflight_json,
    _proof_fields,
    _report,
)

from .metadata import (
    _artifact_mapping,
    _public_gold_for_node,
)

from .node_validation import _validate_node


def validate_manifest(
    manifest: object,
    resources: Iterable[str] | None = None,
    required_language: str = "ko-KR",
) -> tuple[dict[str, object], dict[str, object] | None]:
    """Validate manifest declarations and return ``(report, catalog-or-None)``."""
    if required_language != "ko-KR":
        error = _error(
            "UNSUPPORTED_LANGUAGE", "required_language", "only ko-KR is supported"
        )
        return _report(
            "ERROR",
            [error],
            declared_status="FAIL",
            required_language=required_language,
        ), None
    try:
        _preflight_json(manifest)
        root = _artifact_mapping(manifest, "manifest")
        metadata = _artifact_mapping(root.get("metadata"), "metadata")
        schema_version = metadata.get("dbt_schema_version")
        if not isinstance(schema_version, str) or not schema_version.endswith(
            MANIFEST_V12_SUFFIX
        ):
            raise ArtifactShapeError(
                "UNSUPPORTED_MANIFEST_VERSION",
                "metadata.dbt_schema_version",
                "dbt manifest schema v12 is required",
            )
        nodes = _artifact_mapping(root.get("nodes"), "nodes")
        exposures = _artifact_mapping(root.get("exposures"), "exposures")
        for uid, node in nodes.items():
            if not isinstance(uid, str) or not isinstance(node, dict):
                raise ArtifactShapeError(
                    "INVALID_ARTIFACT_SHAPE",
                    "nodes",
                    "node keys and values must be string/mapping pairs",
                )
        for exposure_uid, exposure in exposures.items():
            if not isinstance(exposure_uid, str) or not isinstance(exposure, dict):
                raise ArtifactShapeError(
                    "INVALID_ARTIFACT_SHAPE",
                    "exposures",
                    "exposure keys and values must be string/mapping pairs",
                )
    except ArtifactShapeError as error:
        detail = _error(error.code, error.path, error.message)
        return _report(
            "ERROR",
            [detail],
            declared_status="FAIL",
            required_language=required_language,
        ), None

    governed: dict[
        str, tuple[Mapping[str, object], dict[str, object], str, list[dict[str, str]]]
    ] = {}
    for uid in sorted(nodes):
        node = nodes[uid]
        if node.get("resource_type") != "model":
            continue
        public_gold, public_gold_path, discovery_errors = _public_gold_for_node(
            node, f"nodes.{uid}"
        )
        if public_gold is not None:
            governed[uid] = (node, public_gold, public_gold_path, discovery_errors)

    selector_errors: list[dict[str, str]] = []
    selected_uids: set[str] = set()
    selectors = sorted(set(resources or []))
    if selectors:
        for selector in selectors:
            matches = [
                uid
                for uid, (node, _, _, _) in governed.items()
                if uid == selector or node.get("name") == selector
            ]
            if not matches:
                selector_errors.append(
                    _error(
                        "RESOURCE_NOT_FOUND",
                        f"resources.{selector}",
                        "resource selector did not resolve",
                    )
                )
            elif len(matches) > 1:
                selector_errors.append(
                    _error(
                        "RESOURCE_AMBIGUOUS",
                        f"resources.{selector}",
                        "resource selector is ambiguous",
                    )
                )
            else:
                selected_uids.add(matches[0])
    else:
        selected_uids.update(governed)

    errors = list(selector_errors)
    exported: list[dict[str, object]] = []
    for uid in sorted(selected_uids):
        node, public_gold, public_gold_path, discovery_errors = governed[uid]
        errors.extend(discovery_errors)
        node_errors, resource, visibility = _validate_node(
            uid, node, public_gold, public_gold_path, nodes, exposures
        )
        errors.extend(node_errors)
        if visibility in PUBLIC_VISIBILITIES:
            exported.append(resource)

    if errors:
        return (
            _report(
                "FAIL",
                errors,
                declared_status="FAIL",
                required_language=required_language,
                resources=selected_uids,
            ),
            None,
        )
    report = _report(
        "PASS",
        [],
        declared_status="PASS",
        required_language=required_language,
        resources=selected_uids,
    )
    catalog: dict[str, object] = {
        "catalog_schema_version": CATALOG_SCHEMA_VERSION,
        "documentation_language": required_language,
        "resources": sorted(exported, key=lambda item: str(item["unique_id"])),
    }
    catalog.update(_proof_fields("PASS"))
    return report, catalog
