"""Internal _manifest_contract node_validation responsibility."""

from __future__ import annotations

import copy
from typing import Mapping

from .foundation import (
    KOREAN_FIELDS,
    MISSING,
    PUBLIC_GOLD_EXPORT_FIELDS,
    SAFE_KEY_ROLES,
    STRUCTURED_FIELDS,
    VALID_CONTRACT_STATUSES,
    VALID_MATURITIES,
    VALID_VISIBILITIES,
    _error,
    _unsafe_contract_errors,
)

from .lineage_rules import (
    _validate_joins,
    _validate_lifecycle,
    _validate_lineage,
)

from .metadata import (
    _column_meta,
    _effective_contract_enforcement,
    _korean_text,
    _nonempty_string,
    _validated_column_order,
)

from .publication import _validate_publication

from .semantic_rules import (
    _validate_metrics,
    _validate_quality,
)

from .space_rules import _validate_space

from .time_rules import _validate_time


def _validate_node(
    uid: str,
    node: Mapping[str, object],
    public_gold: Mapping[str, object],
    public_gold_path: str,
    nodes: Mapping[str, object],
    exposures: Mapping[str, object],
) -> tuple[list[dict[str, str]], dict[str, object], str | None]:
    base = f"nodes.{uid}"
    errors: list[dict[str, str]] = []
    name = _nonempty_string(node, "name", f"{base}.name", errors) or uid
    description = (
        _korean_text(
            node, "description", f"{base}.description", errors, identifier=name
        )
        or ""
    )
    declared_uid = node.get("unique_id", uid)
    if declared_uid != uid:
        errors.append(
            _error(
                "UNIQUE_ID_MISMATCH",
                f"{base}.unique_id",
                "node unique_id must match its mapping key",
            )
        )

    _nonempty_string(
        public_gold, "contract_version", f"{public_gold_path}.contract_version", errors
    )
    language = _nonempty_string(
        public_gold,
        "documentation_language",
        f"{public_gold_path}.documentation_language",
        errors,
    )
    if language is not None and language != "ko-KR":
        errors.append(
            _error(
                "LANGUAGE_MISMATCH",
                f"{public_gold_path}.documentation_language",
                "documentation_language must equal ko-KR",
            )
        )
    for field in KOREAN_FIELDS:
        _korean_text(public_gold, field, f"{public_gold_path}.{field}", errors)
    _korean_text(public_gold, "owner", f"{public_gold_path}.owner", errors)

    maturity = public_gold.get("maturity")
    if maturity not in VALID_MATURITIES:
        errors.append(
            _error(
                "INVALID_VALUE",
                f"{public_gold_path}.maturity",
                "maturity must be low, medium, or high",
            )
        )
    visibility = public_gold.get("visibility")
    if visibility not in VALID_VISIBILITIES:
        errors.append(
            _error(
                "INVALID_VALUE",
                f"{public_gold_path}.visibility",
                "visibility is not supported",
            )
        )
        visibility = None
    contract_status = public_gold.get("contract_status")
    if contract_status not in VALID_CONTRACT_STATUSES:
        errors.append(
            _error(
                "INVALID_VALUE",
                f"{public_gold_path}.contract_status",
                "contract_status is not supported",
            )
        )
        contract_status = None
    for field in STRUCTURED_FIELDS:
        if not isinstance(public_gold.get(field), dict):
            errors.append(
                _error(
                    "INVALID_TYPE",
                    f"{public_gold_path}.{field}",
                    f"{field} must be a mapping",
                )
            )
    errors.extend(_unsafe_contract_errors(public_gold, public_gold_path))

    primary_key_value = public_gold.get("primary_key")
    primary_keys: list[str] = []
    if (
        not isinstance(primary_key_value, list)
        or not primary_key_value
        or any(
            not isinstance(item, str) or not item.strip() for item in primary_key_value
        )
    ):
        errors.append(
            _error(
                "INVALID_PRIMARY_KEY",
                f"{public_gold_path}.primary_key",
                "primary_key must be a nonempty ordered list of column names",
            )
        )
    else:
        primary_keys = [item.strip() for item in primary_key_value]
        if len(set(primary_keys)) != len(primary_keys):
            errors.append(
                _error(
                    "INVALID_PRIMARY_KEY",
                    f"{public_gold_path}.primary_key",
                    "primary_key names must be unique",
                )
            )

    dbt_enforced, enforcement_path = _effective_contract_enforcement(node, base, errors)
    if contract_status == "enforced" and not dbt_enforced:
        errors.append(
            _error(
                "CONTRACT_NOT_ENFORCED",
                enforcement_path,
                "contract_status enforced requires effective dbt contract enforcement",
            )
        )

    columns_value = node.get("columns", MISSING)
    if not isinstance(columns_value, dict):
        errors.append(
            _error("INVALID_TYPE", f"{base}.columns", "columns must be a mapping")
        )
        columns: Mapping[str, object] = {}
    else:
        columns = columns_value
    for key in primary_keys:
        if key not in columns:
            errors.append(
                _error(
                    "UNKNOWN_PRIMARY_KEY_COLUMN",
                    f"{public_gold_path}.primary_key",
                    f"primary key column is not declared: {key}",
                )
            )

    declared_column_names = {key for key in columns if isinstance(key, str)}
    column_order_error_count = len(errors)
    column_order = _validated_column_order(
        public_gold.get("column_order", MISSING),
        f"{public_gold_path}.column_order",
        declared_column_names,
        errors,
    )
    column_iteration_order = (
        column_order
        if len(errors) == column_order_error_count
        else sorted(columns, key=str)
    )

    exported_columns: list[dict[str, object]] = []
    column_data_types_by_name: dict[str, str] = {}
    column_meta_by_name: dict[str, dict[str, object]] = {}
    column_meta_provenance_by_name: dict[str, dict[str, str]] = {}
    column_meta_defaults_by_name: dict[str, str] = {}
    column_descriptions_by_name: dict[str, str] = {}
    for column_name in column_iteration_order:
        column_base = f"{base}.columns.{column_name}"
        column_value = columns[column_name]
        if not isinstance(column_name, str) or not isinstance(column_value, dict):
            errors.append(
                _error(
                    "INVALID_TYPE", column_base, "column entries must be named mappings"
                )
            )
            continue
        declared_name = column_value.get("name", column_name)
        if declared_name != column_name:
            errors.append(
                _error(
                    "COLUMN_NAME_MISMATCH",
                    f"{column_base}.name",
                    "column.name must match its mapping key",
                )
            )
        column_description = (
            _korean_text(
                column_value,
                "description",
                f"{column_base}.description",
                errors,
                identifier=column_name,
            )
            or ""
        )
        data_type = (
            _nonempty_string(
                column_value, "data_type", f"{column_base}.data_type", errors
            )
            or ""
        )
        column_data_types_by_name[column_name] = data_type
        meta, meta_provenance, meta_default_base, meta_errors = _column_meta(
            column_value, column_base
        )
        errors.extend(meta_errors)
        column_meta_by_name[column_name] = meta
        column_meta_provenance_by_name[column_name] = meta_provenance
        column_meta_defaults_by_name[column_name] = meta_default_base
        column_descriptions_by_name[column_name] = column_description

        def meta_path(key: str) -> str:
            return meta_provenance.get(key, f"{meta_default_base}.{key}")

        semantic_role = _nonempty_string(
            meta, "semantic_role", meta_path("semantic_role"), errors
        )
        null_meaning = _korean_text(
            meta, "null_meaning", meta_path("null_meaning"), errors
        )
        exported_meta: dict[str, object] = {}
        if semantic_role is not None:
            exported_meta["semantic_role"] = semantic_role
        if null_meaning is not None:
            exported_meta["null_meaning"] = null_meaning
        nullable = meta.get("nullable", MISSING)
        if nullable is not MISSING:
            if not isinstance(nullable, bool):
                errors.append(
                    _error(
                        "INVALID_TYPE",
                        meta_path("nullable"),
                        "nullable must be boolean when present",
                    )
                )
            else:
                exported_meta["nullable"] = nullable
        if column_name in primary_keys:
            if semantic_role not in SAFE_KEY_ROLES:
                errors.append(
                    _error(
                        "UNSAFE_PRIMARY_KEY_ROLE",
                        meta_path("semantic_role"),
                        "primary-key columns require a safe key or join role",
                    )
                )
            if meta.get("nullable") is not False:
                errors.append(
                    _error(
                        "NULLABLE_PRIMARY_KEY",
                        meta_path("nullable"),
                        "primary-key columns must declare nullable false",
                    )
                )
        optional_validators = (
            ("unit", _nonempty_string),
            ("zero_meaning", _korean_text),
            ("aggregation_behavior", _nonempty_string),
        )
        for field, validator in optional_validators:
            if semantic_role != "metric" and field not in meta:
                continue
            validated = validator(meta, field, meta_path(field), errors)
            if validated is not None:
                exported_meta[field] = validated
        exported_columns.append(
            {
                "data_type": data_type,
                "description": column_description,
                "meta": {key: exported_meta[key] for key in sorted(exported_meta)},
                "name": column_name,
            }
        )

    time_errors, time_projection = _validate_time(
        public_gold.get("time"),
        f"{public_gold_path}.time",
        declared_column_names,
        column_data_types_by_name,
        column_meta_by_name,
        column_meta_provenance_by_name,
        column_meta_defaults_by_name,
        column_descriptions_by_name,
    )
    errors.extend(time_errors)
    space_errors, space_projection = _validate_space(
        uid,
        node,
        public_gold.get("space"),
        f"{public_gold_path}.space",
        declared_column_names,
        nodes,
    )
    errors.extend(space_errors)
    metric_errors, metric_projection = _validate_metrics(
        public_gold.get("metrics"),
        f"{public_gold_path}.metrics",
        declared_column_names,
        column_meta_by_name,
    )
    errors.extend(metric_errors)
    quality_errors, quality_projection = _validate_quality(
        public_gold.get("quality"),
        f"{public_gold_path}.quality",
        declared_column_names,
    )
    errors.extend(quality_errors)
    lineage_errors, lineage_projection = _validate_lineage(
        public_gold.get("lineage"),
        f"{public_gold_path}.lineage",
        declared_column_names,
    )
    errors.extend(lineage_errors)

    publication_errors, publication_projection, exposure_projection = (
        _validate_publication(uid, public_gold, public_gold_path, visibility, exposures)
    )
    errors.extend(publication_errors)
    join_errors, join_projection = _validate_joins(
        uid,
        public_gold.get("joins"),
        f"{public_gold_path}.joins",
        declared_column_names,
        nodes,
    )
    errors.extend(join_errors)
    lifecycle_errors, lifecycle_projection = _validate_lifecycle(
        public_gold.get("lifecycle"), f"{public_gold_path}.lifecycle"
    )
    errors.extend(lifecycle_errors)

    depends_on = node.get("depends_on", {})
    direct_dependencies: list[str] = []
    if not isinstance(depends_on, dict) or not isinstance(
        depends_on.get("nodes", []), list
    ):
        errors.append(
            _error(
                "INVALID_TYPE",
                f"{base}.depends_on.nodes",
                "direct dependencies must be a list",
            )
        )
    else:
        dependency_values = depends_on.get("nodes", [])
        if any(not isinstance(item, str) or not item for item in dependency_values):
            errors.append(
                _error(
                    "INVALID_TYPE",
                    f"{base}.depends_on.nodes",
                    "dependency IDs must be nonempty strings",
                )
            )
        else:
            direct_dependencies = sorted(set(dependency_values))

    exported_public_gold = {
        key: copy.deepcopy(public_gold[key])
        for key in sorted(PUBLIC_GOLD_EXPORT_FIELDS & public_gold.keys())
    }
    exported_public_gold["column_order"] = column_order
    exported_public_gold.update(publication_projection)
    exported_public_gold["lineage"] = lineage_projection
    exported_public_gold["metrics"] = metric_projection
    exported_public_gold["joins"] = join_projection
    exported_public_gold["lifecycle"] = lifecycle_projection
    exported_public_gold["quality"] = quality_projection
    exported_public_gold["space"] = space_projection
    exported_public_gold["time"] = time_projection
    resource = {
        "columns": exported_columns,
        "contract_status": contract_status or "",
        "description": description,
        "direct_dependencies": direct_dependencies,
        "name": name,
        "public_gold": exported_public_gold,
        "unique_id": uid,
    }
    if visibility == "served":
        resource["exposures"] = exposure_projection
    return errors, resource, visibility if isinstance(visibility, str) else None
