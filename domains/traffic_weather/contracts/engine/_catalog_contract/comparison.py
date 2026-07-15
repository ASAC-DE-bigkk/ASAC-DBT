"""Internal _catalog_contract comparison responsibility."""

from __future__ import annotations

import re
from typing import Iterable, Mapping, Sequence

from contracts.engine._manifest_contract import foundation as manifest_validator
from contracts.engine._manifest_contract.service import validate_manifest

from .parsing import (
    _mapping,
    _nonempty_string,
    _validated_catalog,
)

from .reporting import (
    _error,
    _report,
    _validate_evidence_argument,
)


def _normalize_type(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.strip().casefold())
    normalized = re.sub(r"\s*\(\s*", "(", normalized)
    normalized = re.sub(r"\s*,\s*", ",", normalized)
    normalized = re.sub(r"\s*\)", ")", normalized)
    return {"int": "integer", "double precision": "double"}.get(normalized, normalized)


def _comparison_errors(
    declared_resources: Sequence[Mapping[str, object]],
    catalog_nodes: Mapping[str, object],
) -> list[dict[str, object]]:
    errors: list[dict[str, object]] = []
    for resource in sorted(declared_resources, key=lambda item: str(item["unique_id"])):
        uid = str(resource["unique_id"])
        physical_node = catalog_nodes.get(uid)
        if physical_node is None:
            errors.append(
                _error(
                    "MISSING_PHYSICAL_RELATION",
                    f"catalog.nodes.{uid}",
                    "declared public relation is missing from catalog.nodes",
                    uid=uid,
                    column=None,
                )
            )
            continue
        physical_columns = physical_node["columns"]
        declared_columns = {
            str(column["name"]): column for column in resource["columns"]
        }
        declared_order = list(resource["public_gold"]["column_order"])
        declared_names = set(declared_columns)
        physical_names = set(physical_columns)
        for column_name in sorted(declared_names - physical_names):
            errors.append(
                _error(
                    "MISSING_PHYSICAL_COLUMN",
                    f"catalog.nodes.{uid}.columns.{column_name}",
                    "declared column is missing from the physical catalog relation",
                    uid=uid,
                    column=column_name,
                    declared_type=declared_columns[column_name]["data_type"],
                    physical_type=None,
                )
            )
        for column_name in sorted(physical_names - declared_names):
            physical_column = physical_columns[column_name]
            errors.append(
                _error(
                    "EXTRA_PHYSICAL_COLUMN",
                    f"catalog.nodes.{uid}.columns.{column_name}",
                    "physical catalog column is not present in the declaration",
                    uid=uid,
                    column=column_name,
                    declared_type=None,
                    physical_type=physical_column["type"],
                    physical_index=physical_column["index"],
                )
            )
        for column_name in sorted(declared_names & physical_names):
            declared_type = str(declared_columns[column_name]["data_type"])
            physical_type = str(physical_columns[column_name]["type"])
            if _normalize_type(declared_type) != _normalize_type(physical_type):
                errors.append(
                    _error(
                        "INCOMPATIBLE_COLUMN_TYPE",
                        f"catalog.nodes.{uid}.columns.{column_name}.type",
                        "declared and physical catalog column types are incompatible",
                        uid=uid,
                        column=column_name,
                        declared_type=declared_type,
                        physical_type=physical_type,
                        physical_index=physical_columns[column_name]["index"],
                    )
                )

        index_to_columns: dict[int, list[str]] = {}
        for column_name in sorted(physical_columns):
            index = physical_columns[column_name]["index"]
            index_to_columns.setdefault(index, []).append(column_name)
        for index in sorted(index_to_columns):
            duplicate_columns = index_to_columns[index]
            if len(duplicate_columns) < 2:
                continue
            for column_name in duplicate_columns:
                errors.append(
                    _error(
                        "DUPLICATE_PHYSICAL_INDEX",
                        f"catalog.nodes.{uid}.columns.{column_name}.index",
                        "physical catalog column index is duplicated",
                        uid=uid,
                        column=column_name,
                        physical_index=index,
                    )
                )
        ordered_physical = sorted(
            physical_columns,
            key=lambda name: (physical_columns[name]["index"], name),
        )
        expected_indexes = list(range(1, len(physical_columns) + 1))
        actual_indexes = [physical_columns[name]["index"] for name in ordered_physical]
        if actual_indexes != expected_indexes:
            for expected_index, column_name in enumerate(ordered_physical, start=1):
                physical_index = physical_columns[column_name]["index"]
                if physical_index == expected_index:
                    continue
                errors.append(
                    _error(
                        "NONCONTIGUOUS_PHYSICAL_INDEX",
                        f"catalog.nodes.{uid}.columns.{column_name}.index",
                        "physical catalog indexes must be exactly contiguous from 1 through N",
                        uid=uid,
                        column=column_name,
                        expected_index=expected_index,
                        physical_index=physical_index,
                    )
                )
        elif declared_names == physical_names and ordered_physical != declared_order:
            physical_positions = {
                column_name: physical_columns[column_name]["index"]
                for column_name in ordered_physical
            }
            for declared_index, column_name in enumerate(declared_order, start=1):
                physical_index = physical_positions[column_name]
                if declared_index == physical_index:
                    continue
                errors.append(
                    _error(
                        "PHYSICAL_COLUMN_ORDER_MISMATCH",
                        f"catalog.nodes.{uid}.columns.{column_name}.index",
                        "physical catalog order differs from public_gold.column_order",
                        uid=uid,
                        column=column_name,
                        declared_index=declared_index,
                        physical_index=physical_index,
                    )
                )
    return errors


def compare_public_gold_catalog(
    manifest: object,
    catalog: object,
    resources: Iterable[str] | None = None,
    required_language: str = "ko-KR",
    evidence_kind: str = "fixture",
    evidence_id: str | None = None,
) -> dict[str, object]:
    normalized_evidence_id, evidence_error = _validate_evidence_argument(
        evidence_kind, evidence_id
    )
    if evidence_error is not None:
        return _report(
            "ERROR",
            [evidence_error],
            declared_status="NOT_RUN",
            comparison_status="NOT_RUN",
            evidence_kind=evidence_kind,
            evidence_id=None,
            required_language=required_language,
        )

    selected = list(resources) if resources is not None else None
    declared_report, declared_catalog = validate_manifest(
        manifest, resources=selected, required_language=required_language
    )
    if declared_report["status"] != "PASS":
        validator_status = str(declared_report["status"])
        declared_status = "FAIL" if validator_status == "FAIL" else "NOT_RUN"
        return _report(
            validator_status,
            declared_report.get("errors", []),
            declared_status=declared_status,
            comparison_status="NOT_RUN",
            evidence_kind=evidence_kind,
            evidence_id=normalized_evidence_id,
            required_language=required_language,
            resources=declared_report.get("resources", []),
        )

    if declared_catalog is None:
        return _report(
            "ERROR",
            [
                _error(
                    "DECLARED_CATALOG_MISSING",
                    "manifest",
                    "validator did not produce declarations",
                )
            ],
            declared_status="PASS",
            comparison_status="NOT_RUN",
            evidence_kind=evidence_kind,
            evidence_id=normalized_evidence_id,
            required_language=required_language,
        )
    declared_resources = list(declared_catalog["resources"])
    declared_uids = [str(resource["unique_id"]) for resource in declared_resources]
    if selected is not None:
        nonpublishable = sorted(
            set(declared_report.get("resources", [])) - set(declared_uids)
        )
        if nonpublishable:
            return _report(
                "FAIL",
                [
                    _error(
                        "RESOURCE_NOT_PUBLISHABLE",
                        f"nodes.{uid}.config.meta.public_gold.visibility",
                        "selected resource is not published_producer or served",
                        uid=uid,
                        column=None,
                    )
                    for uid in nonpublishable
                ],
                declared_status="PASS",
                comparison_status="NOT_RUN",
                evidence_kind=evidence_kind,
                evidence_id=normalized_evidence_id,
                required_language=required_language,
                resources=nonpublishable,
            )
    if not declared_resources:
        return _report(
            "FAIL",
            [
                _error(
                    "NO_PUBLISHABLE_RESOURCES",
                    "resources",
                    "no published_producer or served resources were selected",
                )
            ],
            declared_status="PASS",
            comparison_status="NOT_RUN",
            evidence_kind=evidence_kind,
            evidence_id=normalized_evidence_id,
            required_language=required_language,
        )

    try:
        catalog_metadata, catalog_nodes = _validated_catalog(catalog)
        manifest_root = _mapping(manifest, "manifest")
        manifest_metadata = _mapping(manifest_root.get("metadata"), "manifest.metadata")
        manifest_invocation_id = _nonempty_string(
            manifest_metadata.get("invocation_id"),
            "MISSING_INVOCATION_ID",
            "manifest.metadata.invocation_id",
            "manifest invocation_id must be a nonempty string",
        )
        catalog_invocation_id = _nonempty_string(
            catalog_metadata.get("invocation_id"),
            "MISSING_INVOCATION_ID",
            "catalog.metadata.invocation_id",
            "catalog invocation_id must be a nonempty string",
        )
        if manifest_invocation_id != catalog_invocation_id:
            raise manifest_validator.ArtifactShapeError(
                "INVOCATION_ID_MISMATCH",
                "catalog.metadata.invocation_id",
                "manifest and catalog invocation_id values must match exactly",
            )
    except manifest_validator.ArtifactShapeError as error:
        return _report(
            "ERROR",
            [_error(error.code, error.path, error.message)],
            declared_status="PASS",
            comparison_status="NOT_RUN",
            evidence_kind=evidence_kind,
            evidence_id=normalized_evidence_id,
            required_language=required_language,
            resources=declared_uids,
        )

    differences = _comparison_errors(declared_resources, catalog_nodes)
    comparison_status = "FAIL" if differences else "PASS"
    return _report(
        comparison_status,
        differences,
        declared_status="PASS",
        comparison_status=comparison_status,
        evidence_kind=evidence_kind,
        evidence_id=normalized_evidence_id,
        required_language=required_language,
        resources=declared_uids,
    )
