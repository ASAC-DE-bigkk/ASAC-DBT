"""Internal _manifest_contract lineage_rules responsibility."""

from __future__ import annotations

from typing import Mapping

from .foundation import (
    LINEAGE_IDENTIFIER_CLASSES,
    MISSING,
    SAFE_JOIN_CARDINALITIES,
    _error,
)

from .metadata import (
    _korean_text,
    _nonempty_string,
    _validated_string_list,
)

from .publication import _test_nodes_named


def _validate_lineage(
    value: object, path: str, column_names: set[str]
) -> tuple[list[dict[str, str]], dict[str, object]]:
    errors: list[dict[str, str]] = []
    projection: dict[str, object] = {}
    if not isinstance(value, dict):
        return errors, projection
    projection["source_relations"] = _validated_string_list(
        value.get("source_relations", MISSING),
        f"{path}.source_relations",
        errors,
        minimum=1,
    )
    identifiers_value = value.get("identifiers", MISSING)
    if not isinstance(identifiers_value, dict):
        errors.append(
            _error(
                "INVALID_TYPE", f"{path}.identifiers", "identifiers must be a mapping"
            )
        )
        identifiers: Mapping[str, object] = {}
    else:
        identifiers = identifiers_value
    projected_identifiers: dict[str, object] = {}
    for identifier_class in LINEAGE_IDENTIFIER_CLASSES:
        identifier_path = f"{path}.identifiers.{identifier_class}"
        identifier_value = identifiers.get(identifier_class, MISSING)
        if not isinstance(identifier_value, dict):
            errors.append(
                _error(
                    "MISSING_LINEAGE_IDENTIFIER",
                    identifier_path,
                    "required lineage identifier class must be a mapping",
                )
            )
            continue
        relation_only_value = identifier_value.get("relation_level_only", MISSING)
        relation_only = False
        if relation_only_value is not MISSING:
            if not isinstance(relation_only_value, bool):
                errors.append(
                    _error(
                        "INVALID_TYPE",
                        f"{identifier_path}.relation_level_only",
                        "relation_level_only must be boolean",
                    )
                )
            else:
                relation_only = relation_only_value
        columns_value = identifier_value.get("columns", MISSING)
        if relation_only:
            if columns_value is MISSING:
                columns: list[str] = []
            elif columns_value == []:
                columns = []
            else:
                _validated_string_list(
                    columns_value,
                    f"{identifier_path}.columns",
                    errors,
                    minimum=0,
                )
                errors.append(
                    _error(
                        "RELATION_LEVEL_COLUMNS_CONFLICT",
                        f"{identifier_path}.columns",
                        "relation-level-only identifiers must omit columns or declare an empty list",
                    )
                )
                columns = []
        else:
            columns = _validated_string_list(
                columns_value,
                f"{identifier_path}.columns",
                errors,
                minimum=1,
            )
        if not relation_only and any(column not in column_names for column in columns):
            errors.append(
                _error(
                    "UNKNOWN_LINEAGE_COLUMN",
                    f"{identifier_path}.columns",
                    "lineage columns must be declared model columns",
                )
            )
        projected_identifier: dict[str, object] = {"columns": columns}
        if relation_only_value is not MISSING and isinstance(relation_only_value, bool):
            projected_identifier["relation_level_only"] = relation_only
        projected_identifiers[identifier_class] = projected_identifier
    projection["identifiers"] = projected_identifiers
    return errors, projection


def _validate_joins(
    uid: str,
    value: object,
    path: str,
    column_names: set[str],
    nodes: Mapping[str, object],
) -> tuple[list[dict[str, str]], dict[str, object]]:
    errors: list[dict[str, str]] = []
    projection: dict[str, object] = {}
    if not isinstance(value, dict):
        return errors, projection
    for join_name in sorted(value):
        join_path = f"{path}.{join_name}"
        join = value[join_name]
        if (
            not isinstance(join_name, str)
            or not join_name.strip()
            or not isinstance(join, dict)
        ):
            errors.append(
                _error("INVALID_JOIN", join_path, "join entries must be named mappings")
            )
            continue
        target = _nonempty_string(join, "target", f"{join_path}.target", errors) or ""
        source_keys_value = join.get("source_keys", MISSING)
        if (
            not isinstance(source_keys_value, list)
            or not source_keys_value
            or any(
                not isinstance(item, str) or not item.strip()
                for item in source_keys_value
            )
        ):
            errors.append(
                _error(
                    "INVALID_JOIN_SOURCE_KEYS",
                    f"{join_path}.source_keys",
                    "source_keys must be a nonempty ordered string list",
                )
            )
            source_keys: list[str] = []
        else:
            source_keys = [item.strip() for item in source_keys_value]
            if len(set(source_keys)) != len(source_keys) or any(
                key not in column_names for key in source_keys
            ):
                errors.append(
                    _error(
                        "INVALID_JOIN_SOURCE_KEYS",
                        f"{join_path}.source_keys",
                        "source_keys must be unique declared model columns",
                    )
                )
        purpose = _korean_text(join, "purpose", f"{join_path}.purpose", errors) or ""
        cardinality = (
            _nonempty_string(join, "cardinality", f"{join_path}.cardinality", errors)
            or ""
        )
        if cardinality and cardinality not in SAFE_JOIN_CARDINALITIES:
            errors.append(
                _error(
                    "UNSAFE_JOIN_CARDINALITY",
                    f"{join_path}.cardinality",
                    "only one_to_one and many_to_one are publishable",
                )
            )
        fan_out_policy = (
            _korean_text(join, "fan_out_policy", f"{join_path}.fan_out_policy", errors)
            or ""
        )
        reconciliation = (
            _nonempty_string(
                join, "reconciliation_test", f"{join_path}.reconciliation_test", errors
            )
            or ""
        )
        if reconciliation:
            named_tests = _test_nodes_named(reconciliation, nodes)
            dependent = []
            for _, test_node in named_tests:
                depends_on = test_node.get("depends_on", {})
                dependency_nodes = (
                    depends_on.get("nodes", []) if isinstance(depends_on, dict) else []
                )
                if isinstance(dependency_nodes, list) and uid in dependency_nodes:
                    dependent.append(test_node)
            if len(dependent) != 1:
                if not named_tests:
                    code = "RECONCILIATION_TEST_NOT_FOUND"
                elif not dependent:
                    code = "RECONCILIATION_TEST_DEPENDENCY"
                else:
                    code = "RECONCILIATION_TEST_AMBIGUOUS"
                errors.append(
                    _error(
                        code,
                        f"{join_path}.reconciliation_test",
                        "reconciliation test name must resolve uniquely to a test depending on the model",
                    )
                )
        projection[join_name] = {
            "cardinality": cardinality,
            "fan_out_policy": fan_out_policy,
            "purpose": purpose,
            "reconciliation_test": reconciliation,
            "source_keys": source_keys,
            "target": target,
        }
    return errors, projection


def _validate_lifecycle(
    value: object, path: str
) -> tuple[list[dict[str, str]], dict[str, object]]:
    errors: list[dict[str, str]] = []
    projection: dict[str, object] = {}
    if not isinstance(value, dict):
        return errors, projection
    status = value.get("status")
    if status not in {"active", "deprecated"}:
        errors.append(
            _error(
                "INVALID_LIFECYCLE_STATUS",
                f"{path}.status",
                "lifecycle status must be active or deprecated",
            )
        )
    else:
        projection["status"] = status
    replacement_value = value.get("replacement_relation", MISSING)
    replacement: str | None = None
    if replacement_value is not MISSING:
        replacement = _nonempty_string(
            value, "replacement_relation", f"{path}.replacement_relation", errors
        )
        if replacement is not None:
            projection["replacement_relation"] = replacement
    future_value = value.get("replacement_is_future", MISSING)
    if future_value is not MISSING:
        if not isinstance(future_value, bool):
            errors.append(
                _error(
                    "INVALID_TYPE",
                    f"{path}.replacement_is_future",
                    "replacement_is_future must be boolean",
                )
            )
        else:
            projection["replacement_is_future"] = future_value
    if status == "deprecated":
        if replacement is None:
            errors.append(
                _error(
                    "MISSING_REPLACEMENT",
                    f"{path}.replacement_relation",
                    "deprecated requires a replacement relation",
                )
            )
        guidance = _korean_text(
            value,
            "compatibility_window_guidance",
            f"{path}.compatibility_window_guidance",
            errors,
        )
        if guidance is not None:
            projection["compatibility_window_guidance"] = guidance
    elif status == "active" and replacement is not None and future_value is not True:
        errors.append(
            _error(
                "UNMARKED_FUTURE_REPLACEMENT",
                f"{path}.replacement_is_future",
                "active replacement must be explicitly marked future",
            )
        )
    return errors, projection
