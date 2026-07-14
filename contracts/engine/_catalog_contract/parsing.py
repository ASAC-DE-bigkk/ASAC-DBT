"""Internal _catalog_contract parsing responsibility."""

from __future__ import annotations

from typing import Mapping

from contracts.engine._manifest_contract import foundation as manifest_validator

CATALOG_V1_SUFFIX = "/dbt/catalog/v1.json"


MISSING = object()


def _mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise manifest_validator.ArtifactShapeError(
            "INVALID_ARTIFACT_SHAPE", path, f"{path} must be a mapping"
        )
    return value


def _nonempty_string(value: object, code: str, path: str, message: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise manifest_validator.ArtifactShapeError(code, path, message)
    return value


def _validated_catalog(
    catalog: object,
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    manifest_validator._preflight_json(catalog, "catalog")
    root = _mapping(catalog, "catalog")
    metadata = _mapping(root.get("metadata"), "catalog.metadata")
    schema_version = metadata.get("dbt_schema_version")
    if not isinstance(schema_version, str) or not schema_version.endswith(
        CATALOG_V1_SUFFIX
    ):
        raise manifest_validator.ArtifactShapeError(
            "UNSUPPORTED_CATALOG_VERSION",
            "catalog.metadata.dbt_schema_version",
            "dbt catalog schema v1 is required",
        )
    nodes = _mapping(root.get("nodes"), "catalog.nodes")
    catalog_errors = root.get("errors", MISSING)
    if catalog_errors not in (MISSING, None, []):
        if isinstance(catalog_errors, list):
            raise manifest_validator.ArtifactShapeError(
                "CATALOG_ERRORS_PRESENT",
                "catalog.errors",
                "catalog errors must be absent or empty",
            )
        raise manifest_validator.ArtifactShapeError(
            "INVALID_ARTIFACT_SHAPE",
            "catalog.errors",
            "catalog errors must be null or a list",
        )
    for uid in sorted(nodes):
        node = nodes[uid]
        if not isinstance(uid, str) or not isinstance(node, dict):
            raise manifest_validator.ArtifactShapeError(
                "INVALID_ARTIFACT_SHAPE",
                "catalog.nodes",
                "catalog node keys and values must be string/mapping pairs",
            )
        columns = _mapping(node.get("columns"), f"catalog.nodes.{uid}.columns")
        for column_name in sorted(columns):
            column = columns[column_name]
            column_path = f"catalog.nodes.{uid}.columns.{column_name}"
            if not isinstance(column_name, str) or not isinstance(column, dict):
                raise manifest_validator.ArtifactShapeError(
                    "INVALID_ARTIFACT_SHAPE",
                    f"catalog.nodes.{uid}.columns",
                    "catalog column keys and values must be string/mapping pairs",
                )
            if "name" in column and column.get("name") != column_name:
                raise manifest_validator.ArtifactShapeError(
                    "CATALOG_COLUMN_NAME_MISMATCH",
                    f"{column_path}.name",
                    "catalog column.name must match its mapping key",
                )
            _nonempty_string(
                column.get("type"),
                "INVALID_CATALOG_COLUMN_TYPE",
                f"{column_path}.type",
                "catalog column type must be a nonempty string",
            )
            index = column.get("index", MISSING)
            if isinstance(index, bool) or not isinstance(index, int):
                raise manifest_validator.ArtifactShapeError(
                    "INVALID_CATALOG_COLUMN_INDEX",
                    f"{column_path}.index",
                    "catalog column index must be an integer",
                )
    return metadata, nodes
