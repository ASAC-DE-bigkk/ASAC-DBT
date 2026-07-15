"""Internal _manifest_contract metadata responsibility."""

from __future__ import annotations

import copy
from typing import Mapping

from contracts.engine._schema_contract import descriptions as source_lint

from .foundation import (
    ArtifactShapeError,
    MISSING,
    TIMESTAMP_DATA_TYPE_RE,
    _error,
    _json_equal,
    _unsafe_contract_errors,
)


def _artifact_mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ArtifactShapeError(
            "INVALID_ARTIFACT_SHAPE", path, f"{path} must be a mapping"
        )
    return value


def _public_gold_for_node(
    node: Mapping[str, object], base: str
) -> tuple[dict[str, object] | None, str, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    config_value = node.get("config", {})
    config = config_value if isinstance(config_value, dict) else {}
    canonical_meta_value = config.get("meta", MISSING)
    legacy_meta_value = node.get("meta", MISSING)
    canonical_meta = (
        canonical_meta_value if isinstance(canonical_meta_value, dict) else None
    )
    legacy_meta = legacy_meta_value if isinstance(legacy_meta_value, dict) else None
    canonical_value = (
        canonical_meta.get("public_gold", MISSING)
        if canonical_meta is not None
        else MISSING
    )
    legacy_value = (
        legacy_meta.get("public_gold", MISSING) if legacy_meta is not None else MISSING
    )
    if canonical_meta_value is not MISSING and canonical_value is MISSING:
        return None, f"{base}.config.meta.public_gold", []
    if canonical_meta_value is MISSING and legacy_value is MISSING:
        return None, f"{base}.config.meta.public_gold", []

    if not isinstance(config_value, dict):
        errors.append(
            _error("INVALID_TYPE", f"{base}.config", "config must be a mapping")
        )
    if canonical_meta_value is not MISSING and not isinstance(
        canonical_meta_value, dict
    ):
        errors.append(
            _error(
                "INVALID_TYPE",
                f"{base}.config.meta",
                "canonical metadata must be a mapping",
            )
        )
    if legacy_meta_value is not MISSING and not isinstance(legacy_meta_value, dict):
        errors.append(
            _error("INVALID_TYPE", f"{base}.meta", "legacy metadata must be a mapping")
        )
    if (
        canonical_value is not MISSING
        and legacy_value is not MISSING
        and not _json_equal(canonical_value, legacy_value)
    ):
        errors.append(
            _error(
                "CONFLICTING_METADATA",
                f"{base}.config.meta.public_gold",
                "canonical and legacy public_gold metadata conflict",
            )
        )
    chosen = canonical_value if canonical_meta_value is not MISSING else legacy_value
    chosen_path = (
        f"{base}.config.meta.public_gold"
        if canonical_meta_value is not MISSING
        else f"{base}.meta.public_gold"
    )
    if not isinstance(chosen, dict):
        errors.append(
            _error("INVALID_TYPE", chosen_path, "public_gold must be a mapping")
        )
        return {}, chosen_path, errors
    return copy.deepcopy(chosen), chosen_path, errors


def _column_meta(
    column: Mapping[str, object], base: str
) -> tuple[dict[str, object], dict[str, str], str, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    config_value = column.get("config", {})
    config = config_value if isinstance(config_value, dict) else {}
    canonical_value = config.get("meta", MISSING)
    legacy_value = column.get("meta", MISSING)
    if not isinstance(config_value, dict):
        errors.append(
            _error("INVALID_TYPE", f"{base}.config", "column config must be a mapping")
        )
    if canonical_value is not MISSING and not isinstance(canonical_value, dict):
        errors.append(
            _error(
                "INVALID_TYPE",
                f"{base}.config.meta",
                "column metadata must be a mapping",
            )
        )
    if legacy_value is not MISSING and not isinstance(legacy_value, dict):
        errors.append(
            _error(
                "INVALID_TYPE",
                f"{base}.meta",
                "legacy column metadata must be a mapping",
            )
        )
    canonical = canonical_value if isinstance(canonical_value, dict) else {}
    legacy = legacy_value if isinstance(legacy_value, dict) else {}
    if canonical_value is MISSING and legacy_value is MISSING:
        errors.append(
            _error(
                "MISSING_FIELD", f"{base}.config.meta", "column metadata is required"
            )
        )
        return {}, {}, f"{base}.config.meta", errors
    if canonical:
        errors.extend(_unsafe_contract_errors(canonical, f"{base}.config.meta"))
    if legacy:
        errors.extend(_unsafe_contract_errors(legacy, f"{base}.meta"))
    effective = copy.deepcopy(legacy)
    provenance = {key: f"{base}.meta.{key}" for key in legacy}
    default_base = (
        f"{base}.config.meta" if canonical_value is not MISSING else f"{base}.meta"
    )
    for key, value in canonical.items():
        if key in legacy and not _json_equal(legacy[key], value):
            errors.append(
                _error(
                    "CONFLICTING_METADATA",
                    f"{base}.config.meta.{key}",
                    f"canonical and legacy column metadata conflict for {key}",
                )
            )
        effective[key] = copy.deepcopy(value)
        provenance[key] = f"{base}.config.meta.{key}"
    return effective, provenance, default_base, errors


def _nonempty_string(
    mapping: Mapping[str, object], key: str, path: str, errors: list[dict[str, str]]
) -> str | None:
    value = mapping.get(key, MISSING)
    if not isinstance(value, str) or not value.strip():
        errors.append(
            _error("MISSING_OR_INVALID_FIELD", path, f"{key} must be a nonempty string")
        )
        return None
    return value.strip()


def _korean_text(
    mapping: Mapping[str, object],
    key: str,
    path: str,
    errors: list[dict[str, str]],
    *,
    identifier: str | None = None,
) -> str | None:
    value = _nonempty_string(mapping, key, path, errors)
    if value is None:
        return None
    code: str | None = None
    message: str | None = None
    if source_lint._is_placeholder_description(value):
        code, message = "PLACEHOLDER_TEXT", f"{key} must not be placeholder text"
    elif identifier is not None and source_lint._normal_identifier(
        value
    ) == source_lint._normal_identifier(identifier):
        code, message = (
            "IDENTIFIER_ONLY_TEXT",
            f"{key} must not only repeat its identifier",
        )
    elif not source_lint.HANGUL_RE.search(value):
        code, message = "LANGUAGE_MISMATCH", f"{key} must contain Korean text"
    if code is not None and message is not None:
        errors.append(_error(code, path, message))
    return value


def _effective_contract_enforcement(
    node: Mapping[str, object], base: str, errors: list[dict[str, str]]
) -> tuple[bool, str]:
    config_value = node.get("config", {})
    config = config_value if isinstance(config_value, dict) else {}
    canonical_contract = config.get("contract", MISSING)
    legacy_contract = node.get("contract", MISSING)
    canonical_enforced = MISSING
    if canonical_contract is not MISSING:
        if not isinstance(canonical_contract, dict):
            errors.append(
                _error(
                    "INVALID_TYPE",
                    f"{base}.config.contract",
                    "contract must be a mapping",
                )
            )
            return False, f"{base}.config.contract.enforced"
        canonical_enforced = canonical_contract.get("enforced", MISSING)
    legacy_enforced = MISSING
    if canonical_enforced is MISSING and legacy_contract is not MISSING:
        if not isinstance(legacy_contract, dict):
            errors.append(
                _error("INVALID_TYPE", f"{base}.contract", "contract must be a mapping")
            )
            return False, f"{base}.contract.enforced"
        legacy_enforced = legacy_contract.get("enforced", MISSING)
    if canonical_enforced is not MISSING:
        enforced = canonical_enforced
        enforced_path = f"{base}.config.contract.enforced"
    elif legacy_enforced is not MISSING:
        enforced = legacy_enforced
        enforced_path = f"{base}.contract.enforced"
    else:
        return False, f"{base}.config.contract.enforced"
    if not isinstance(enforced, bool):
        errors.append(_error("INVALID_TYPE", enforced_path, "enforced must be boolean"))
        return False, enforced_path
    return enforced, enforced_path


def _validated_string_list(
    value: object,
    path: str,
    errors: list[dict[str, str]],
    *,
    minimum: int,
    korean: bool = False,
) -> list[str]:
    if not isinstance(value, list):
        errors.append(_error("INVALID_TYPE", path, "value must be a list"))
        return []
    validated: list[str] = []
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, str) or not item.strip():
            errors.append(
                _error(
                    "INVALID_VALUE", item_path, "list item must be a nonempty string"
                )
            )
            continue
        text = item.strip()
        if korean and (
            source_lint._is_placeholder_description(text)
            or not source_lint.HANGUL_RE.search(text)
        ):
            errors.append(
                _error("LANGUAGE_MISMATCH", item_path, "list item must be Korean prose")
            )
            continue
        validated.append(text)
    unique = sorted(set(validated))
    if len(unique) < minimum:
        errors.append(
            _error(
                "INSUFFICIENT_ITEMS",
                path,
                f"at least {minimum} distinct values are required",
            )
        )
    return unique


def _is_timestamp_data_type(value: object) -> bool:
    return isinstance(value, str) and bool(
        TIMESTAMP_DATA_TYPE_RE.fullmatch(value.strip())
    )


def _validated_column_order(
    value: object,
    path: str,
    column_names: set[str],
    errors: list[dict[str, str]],
) -> list[str]:
    if not isinstance(value, list) or not value:
        errors.append(
            _error(
                "INVALID_COLUMN_ORDER",
                path,
                "column_order must be a nonempty ordered list of column names",
            )
        )
        return []

    validated: list[str] = []
    indexed_names: list[tuple[int, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, str) or not item.strip():
            errors.append(
                _error(
                    "INVALID_COLUMN_ORDER",
                    item_path,
                    "column_order items must be nonempty column names",
                )
            )
            continue
        column_name = item.strip()
        indexed_names.append((index, column_name))
        if column_name in seen:
            errors.append(
                _error(
                    "DUPLICATE_COLUMN_ORDER",
                    item_path,
                    "column_order must not contain duplicate column names",
                )
            )
            continue
        seen.add(column_name)
        validated.append(column_name)

    for index, column_name in indexed_names:
        if column_name not in column_names:
            errors.append(
                _error(
                    "UNKNOWN_COLUMN_ORDER_COLUMN",
                    f"{path}[{index}]",
                    "column_order must name only declared model columns",
                )
            )
    missing_columns = sorted(column_names - seen)
    if missing_columns:
        errors.append(
            _error(
                "MISSING_COLUMN_ORDER_COLUMN",
                path,
                "column_order must include every declared model column exactly once: "
                + ", ".join(missing_columns),
            )
        )
    return validated
