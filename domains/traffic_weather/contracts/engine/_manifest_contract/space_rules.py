"""Internal _manifest_contract space_rules responsibility."""

from __future__ import annotations

from typing import Mapping

from .foundation import (
    CANONICAL_SPACE_APPROVED_REVISION_DATE,
    CANONICAL_SPACE_SOURCE_CHAIN,
    CANONICAL_SPACE_STAMP_FIELDS,
    MISSING,
    _error,
)

from .metadata import (
    _korean_text,
    _nonempty_string,
)

from .publication import _test_nodes_named


def _validate_space(
    uid: str,
    node: Mapping[str, object],
    value: object,
    path: str,
    column_names: set[str],
    nodes: Mapping[str, object],
) -> tuple[list[dict[str, str]], dict[str, object]]:
    errors: list[dict[str, str]] = []
    projection: dict[str, object] = {}
    if not isinstance(value, dict):
        return errors, projection
    enabled = value.get("enabled", MISSING)
    if not isinstance(enabled, bool):
        errors.append(
            _error("INVALID_TYPE", f"{path}.enabled", "enabled must be boolean")
        )
        return errors, projection
    projection["enabled"] = enabled
    if not enabled:
        return errors, projection

    source_chain = value.get("source_chain", MISSING)
    if source_chain != list(CANONICAL_SPACE_SOURCE_CHAIN):
        errors.append(
            _error(
                "INVALID_SPACE_SOURCE_CHAIN",
                f"{path}.source_chain",
                "source_chain must declare the exact canonical administrative-dong chain",
            )
        )
    projection["source_chain"] = (
        [item.strip() for item in source_chain]
        if isinstance(source_chain, list)
        and all(isinstance(item, str) for item in source_chain)
        else []
    )

    canonical_key = _nonempty_string(
        value, "canonical_key", f"{path}.canonical_key", errors
    )
    if canonical_key is not None and canonical_key != "admin_dong_code":
        errors.append(
            _error(
                "INVALID_SPACE_KEY",
                f"{path}.canonical_key",
                "canonical_key must equal admin_dong_code",
            )
        )
    projection["canonical_key"] = canonical_key or ""
    revision_field = _nonempty_string(
        value, "revision_field", f"{path}.revision_field", errors
    )
    if revision_field is not None and revision_field != "admin_dong_revision_date":
        errors.append(
            _error(
                "INVALID_SPACE_REVISION",
                f"{path}.revision_field",
                "revision_field must equal admin_dong_revision_date",
            )
        )
    projection["revision_field"] = revision_field or ""

    approved_revision_date = _nonempty_string(
        value,
        "approved_revision_date",
        f"{path}.approved_revision_date",
        errors,
    )
    if (
        approved_revision_date is not None
        and approved_revision_date != CANONICAL_SPACE_APPROVED_REVISION_DATE
    ):
        errors.append(
            _error(
                "INVALID_SPACE_APPROVED_REVISION",
                f"{path}.approved_revision_date",
                "approved_revision_date must equal the approved canonical revision 2025-04-01",
            )
        )
    projection["approved_revision_date"] = approved_revision_date or ""

    stamp_fields = value.get("stamp_fields", MISSING)
    if stamp_fields != list(CANONICAL_SPACE_STAMP_FIELDS):
        errors.append(
            _error(
                "INVALID_SPACE_STAMP",
                f"{path}.stamp_fields",
                "stamp_fields must declare the exact five-field canonical stamp",
            )
        )
    projected_stamp = (
        [item.strip() for item in stamp_fields]
        if isinstance(stamp_fields, list)
        and all(isinstance(item, str) for item in stamp_fields)
        else []
    )
    projection["stamp_fields"] = projected_stamp
    for field in projected_stamp:
        if field not in column_names:
            errors.append(
                _error(
                    "UNKNOWN_SPACE_COLUMN",
                    f"{path}.stamp_fields",
                    f"spatial stamp column is not declared: {field}",
                )
            )
    for field, field_name in (
        (canonical_key, "canonical_key"),
        (revision_field, "revision_field"),
    ):
        if field is not None and field not in column_names:
            errors.append(
                _error(
                    "UNKNOWN_SPACE_COLUMN",
                    f"{path}.{field_name}",
                    f"spatial contract column is not declared: {field}",
                )
            )

    for field in (
        "candidate_key_explanation",
        "mapping_version_explanation",
        "null_location_explanation",
        "fan_out_explanation",
    ):
        text = _korean_text(value, field, f"{path}.{field}", errors)
        if text is not None:
            projection[field] = text

    depends_on = node.get("depends_on", {})
    dependency_nodes = (
        depends_on.get("nodes", []) if isinstance(depends_on, dict) else []
    )
    if not isinstance(dependency_nodes, list) or not any(
        isinstance(dependency, str) and dependency.endswith(".dim_admin_dong")
        for dependency in dependency_nodes
    ):
        errors.append(
            _error(
                "MISSING_SPACE_DEPENDENCY",
                f"{path}.dependency",
                "spatial producers must directly depend on dim_admin_dong",
            )
        )

    reconciliation_value = value.get("reconciliation_tests", MISSING)
    reconciliation_tests: list[str] = []
    if (
        not isinstance(reconciliation_value, list)
        or len(reconciliation_value) < 2
        or any(
            not isinstance(item, str) or not item.strip()
            for item in reconciliation_value
        )
        or len({item.strip() for item in reconciliation_value if isinstance(item, str)})
        != len(reconciliation_value)
    ):
        errors.append(
            _error(
                "INVALID_RECONCILIATION_TESTS",
                f"{path}.reconciliation_tests",
                "reconciliation_tests must contain at least two distinct test names",
            )
        )
    else:
        reconciliation_tests = [item.strip() for item in reconciliation_value]
    projection["reconciliation_tests"] = reconciliation_tests
    for index, test_name in enumerate(reconciliation_tests):
        named_tests = _test_nodes_named(test_name, nodes)
        dependent = []
        for _, test_node in named_tests:
            test_depends_on = test_node.get("depends_on", {})
            test_dependencies = (
                test_depends_on.get("nodes", [])
                if isinstance(test_depends_on, dict)
                else []
            )
            if isinstance(test_dependencies, list) and uid in test_dependencies:
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
                    f"{path}.reconciliation_tests[{index}]",
                    "reconciliation test name must resolve uniquely to a test depending on the model",
                )
            )
    return errors, projection
