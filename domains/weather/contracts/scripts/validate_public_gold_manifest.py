#!/usr/bin/env python3
"""Validate declared public-Gold metadata in a dbt manifest v12 artifact."""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Iterable, Mapping, Sequence

try:
    from domains.weather.contracts.scripts.artifact_io import write_utf8_stdout
except ModuleNotFoundError:  # Direct execution from scripts/contracts.
    from artifact_io import write_utf8_stdout

try:
    from domains.weather.contracts.scripts import lint_schema_contract_source as source_lint
except ModuleNotFoundError:  # Direct execution from scripts/contracts.
    import lint_schema_contract_source as source_lint


CATALOG_SCHEMA_VERSION = "public-gold-ai-contract/v1"
MANIFEST_V12_SUFFIX = "/dbt/manifest/v12.json"
CLAIM_LIMITATIONS_KO = (
    "이 검사는 manifest에 선언된 메타데이터만 확인하며 실제 컬럼·타입·순서, "
    "SQL projection, grain, 최신 선택, reconciliation 또는 의미적 진실성을 "
    "증명하지 않습니다."
)
KOREAN_FIELDS = (
    "product_question",
    "row_meaning",
    "grain",
    "anchor_universe",
    "usage_guidance",
    "do_not_use_for",
    "semantic_caveats",
)
STRUCTURED_FIELDS = ("time", "space", "metrics", "joins", "quality", "lineage", "lifecycle")
PUBLIC_GOLD_EXPORT_FIELDS = {
    "contract_version",
    "documentation_language",
    *KOREAN_FIELDS,
    "primary_key",
    "owner",
    "maturity",
    "visibility",
    "contract_status",
}
PUBLIC_VISIBILITIES = {"published_producer", "served"}
VALID_VISIBILITIES = {"internal", "candidate", *PUBLIC_VISIBILITIES}
VALID_MATURITIES = {"low", "medium", "high"}
VALID_CONTRACT_STATUSES = {"dev_pending", "enforced"}
SAFE_KEY_ROLES = {"key", "primary_key", "join_key", "dimension_key", "foreign_key", "identifier"}
SAFE_JOIN_CARDINALITIES = {"one_to_one", "many_to_one"}
CANONICAL_TIMEZONE = "Asia/Seoul"
CANONICAL_SPACE_APPROVED_REVISION_DATE = "2025-04-01"
CANONICAL_SPACE_SOURCE_CHAIN = (
    "iceberg_dev.common.bronze_admin_dong_master",
    "asac_axes.dim_admin_dong",
)
CANONICAL_SPACE_STAMP_FIELDS = (
    "admin_dong_code",
    "admin_dong",
    "gu_code",
    "gu",
    "admin_dong_revision_date",
)
LINEAGE_IDENTIFIER_CLASSES = ("as_of", "publication", "raw", "request", "run")
STABLE_ENUM_TOKEN_RE = re.compile(r"^[a-z][a-z0-9_]*$")
EXPLICIT_UTC_RE = re.compile(
    r"(?<![A-Za-z0-9_])UTC(?![A-Za-z0-9_])", re.IGNORECASE
)
TIMESTAMP_DATA_TYPE_RE = re.compile(
    r"^timestamp(?:\s*\(\s*\d+\s*\))?"
    r"(?:\s+(?:with|without)\s+time\s+zone)?$",
    re.IGNORECASE,
)
MAX_JSON_DEPTH = 64
MAX_JSON_CONTAINERS = 50_000
RUNTIME_TIMESTAMP_RE = re.compile(
    r"(?<!\d)\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?(?!\d)"
)
MISSING = object()


class ArtifactShapeError(Exception):
    def __init__(self, code: str, path: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.path = path
        self.message = message


class CliArgumentError(Exception):
    pass


class ReportArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliArgumentError(message)


def _error(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message, "path": path}


def _child_path(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def _validate_json_string(value: str, path: str, *, mapping_key: bool = False) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        subject = "mapping keys" if mapping_key else "strings"
        raise ArtifactShapeError(
            "INVALID_JSON_VALUE",
            path or "manifest",
            f"JSON {subject} must be encodable as UTF-8",
        ) from error


def _preflight_json(value: object, path: str = "") -> None:
    """Validate JSON types with conservative non-recursive resource bounds."""
    stack: list[tuple[object, str, int]] = [(value, path, 0)]
    containers = 0
    while stack:
        current, current_path, depth = stack.pop()
        if depth > MAX_JSON_DEPTH:
            raise ArtifactShapeError(
                "JSON_LIMIT_EXCEEDED",
                current_path or "manifest",
                f"JSON exceeds maximum depth {MAX_JSON_DEPTH}",
            )
        if isinstance(current, dict):
            containers += 1
            if containers > MAX_JSON_CONTAINERS:
                raise ArtifactShapeError(
                    "JSON_LIMIT_EXCEEDED",
                    current_path or "manifest",
                    f"JSON exceeds maximum container count {MAX_JSON_CONTAINERS}",
                )
            items = list(current.items())
            for key, _ in items:
                if not isinstance(key, str):
                    raise ArtifactShapeError(
                        "INVALID_JSON_VALUE",
                        current_path or "manifest",
                        "JSON mapping keys must be strings",
                    )
                _validate_json_string(key, current_path, mapping_key=True)
            for key, child in sorted(items, key=lambda item: item[0], reverse=True):
                stack.append((child, _child_path(current_path, key), depth + 1))
        elif isinstance(current, list):
            containers += 1
            if containers > MAX_JSON_CONTAINERS:
                raise ArtifactShapeError(
                    "JSON_LIMIT_EXCEEDED",
                    current_path or "manifest",
                    f"JSON exceeds maximum container count {MAX_JSON_CONTAINERS}",
                )
            for index in range(len(current) - 1, -1, -1):
                stack.append((current[index], f"{current_path}[{index}]", depth + 1))
        elif isinstance(current, str):
            _validate_json_string(current, current_path)
        elif current is None or isinstance(current, (bool, int)):
            continue
        elif isinstance(current, float):
            if not math.isfinite(current):
                raise ArtifactShapeError(
                    "INVALID_JSON_VALUE",
                    current_path or "manifest",
                    "JSON numbers must be finite",
                )
        else:
            raise ArtifactShapeError(
                "INVALID_JSON_VALUE",
                current_path or "manifest",
                f"unsupported JSON value type: {type(current).__name__}",
            )


def _json_equal(left: object, right: object) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _json_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _json_equal(left_item, right_item)
            for left_item, right_item in zip(left, right)
        )
    return left == right


def _forbidden_contract_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
    compact = normalized.replace("_", "")
    tokens = set(normalized.split("_")) if normalized else set()
    if compact in {"generatedat", "environmentschema"}:
        return True
    if any(
        marker in compact
        for marker in ("credential", "token", "secret", "password")
    ):
        return True
    if any(marker in compact for marker in ("accesskey", "privatekey", "apikey")):
        return True
    return "path" in tokens or compact.endswith("path")


def _absolute_filesystem_path(value: str) -> bool:
    return (
        value.startswith(("/", "\\\\"))
        or bool(re.match(r"^[A-Za-z]:[\\\\/]", value))
    )


def _unsafe_contract_errors(value: object, path: str) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    stack: list[tuple[object, str]] = [(value, path)]
    while stack:
        current, current_path = stack.pop()
        if isinstance(current, dict):
            for key, child in reversed(list(current.items())):
                child_path = _child_path(current_path, key)
                if _forbidden_contract_key(key):
                    errors.append(
                        _error(
                            "FORBIDDEN_EXPORT_KEY",
                            child_path,
                            "contract metadata contains a dynamic, sensitive, environment, or path key",
                        )
                    )
                stack.append((child, child_path))
        elif isinstance(current, list):
            for index in range(len(current) - 1, -1, -1):
                stack.append((current[index], f"{current_path}[{index}]"))
        elif isinstance(current, str) and _absolute_filesystem_path(current):
            errors.append(
                _error(
                    "ABSOLUTE_FILESYSTEM_PATH",
                    current_path,
                    "contract metadata must not contain absolute filesystem paths",
                )
            )
    return errors


def _proof_fields(declared_status: str) -> dict[str, object]:
    return {
        "claim_limitations_ko": CLAIM_LIMITATIONS_KO,
        "proof": {
            "data_contract": "NOT_RUN",
            "declared_contract": declared_status,
            "manual_semantic_review": "REQUIRED",
            "physical_contract": "NOT_RUN",
            "source_yaml_uniqueness": "NOT_RUN",
        },
        "proof_scope": "manifest_declared_contract",
    }


def _report(
    status: str,
    errors: Iterable[dict[str, str]],
    *,
    declared_status: str,
    required_language: str,
    resources: Iterable[str] = (),
) -> dict[str, object]:
    ordered_errors = sorted(
        errors,
        key=lambda item: (item.get("path", ""), item.get("code", ""), item.get("message", "")),
    )
    report: dict[str, object] = {
        "errors": ordered_errors,
        "required_language": required_language,
        "resources": sorted(set(resources)),
        "status": status,
        "summary": {
            "error_count": len(ordered_errors),
            "resources_checked": len(set(resources)),
        },
    }
    report.update(_proof_fields(declared_status))
    return report


def render_json(value: object) -> str:
    """Render stable readable UTF-8 JSON with exactly one trailing newline."""
    try:
        _preflight_json(value, "json")
    except ArtifactShapeError as error:
        raise ValueError(error.message) from error
    return json.dumps(
        value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
    ) + "\n"


def _artifact_mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ArtifactShapeError("INVALID_ARTIFACT_SHAPE", path, f"{path} must be a mapping")
    return value


def _public_gold_for_node(
    node: Mapping[str, object], base: str
) -> tuple[dict[str, object] | None, str, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    config_value = node.get("config", {})
    config = config_value if isinstance(config_value, dict) else {}
    canonical_meta_value = config.get("meta", MISSING)
    legacy_meta_value = node.get("meta", MISSING)
    canonical_meta = canonical_meta_value if isinstance(canonical_meta_value, dict) else None
    legacy_meta = legacy_meta_value if isinstance(legacy_meta_value, dict) else None
    canonical_value = (
        canonical_meta.get("public_gold", MISSING) if canonical_meta is not None else MISSING
    )
    legacy_value = legacy_meta.get("public_gold", MISSING) if legacy_meta is not None else MISSING
    if canonical_meta_value is not MISSING and canonical_value is MISSING:
        return None, f"{base}.config.meta.public_gold", []
    if canonical_meta_value is MISSING and legacy_value is MISSING:
        return None, f"{base}.config.meta.public_gold", []

    if not isinstance(config_value, dict):
        errors.append(_error("INVALID_TYPE", f"{base}.config", "config must be a mapping"))
    if canonical_meta_value is not MISSING and not isinstance(canonical_meta_value, dict):
        errors.append(
            _error("INVALID_TYPE", f"{base}.config.meta", "canonical metadata must be a mapping")
        )
    if legacy_meta_value is not MISSING and not isinstance(legacy_meta_value, dict):
        errors.append(_error("INVALID_TYPE", f"{base}.meta", "legacy metadata must be a mapping"))
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
        errors.append(_error("INVALID_TYPE", chosen_path, "public_gold must be a mapping"))
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
        errors.append(_error("INVALID_TYPE", f"{base}.config", "column config must be a mapping"))
    if canonical_value is not MISSING and not isinstance(canonical_value, dict):
        errors.append(_error("INVALID_TYPE", f"{base}.config.meta", "column metadata must be a mapping"))
    if legacy_value is not MISSING and not isinstance(legacy_value, dict):
        errors.append(_error("INVALID_TYPE", f"{base}.meta", "legacy column metadata must be a mapping"))
    canonical = canonical_value if isinstance(canonical_value, dict) else {}
    legacy = legacy_value if isinstance(legacy_value, dict) else {}
    if canonical_value is MISSING and legacy_value is MISSING:
        errors.append(_error("MISSING_FIELD", f"{base}.config.meta", "column metadata is required"))
        return {}, {}, f"{base}.config.meta", errors
    if canonical:
        errors.extend(_unsafe_contract_errors(canonical, f"{base}.config.meta"))
    if legacy:
        errors.extend(_unsafe_contract_errors(legacy, f"{base}.meta"))
    effective = copy.deepcopy(legacy)
    provenance = {key: f"{base}.meta.{key}" for key in legacy}
    default_base = f"{base}.config.meta" if canonical_value is not MISSING else f"{base}.meta"
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
        errors.append(_error("MISSING_OR_INVALID_FIELD", path, f"{key} must be a nonempty string"))
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
    elif identifier is not None and source_lint._normal_identifier(value) == source_lint._normal_identifier(identifier):
        code, message = "IDENTIFIER_ONLY_TEXT", f"{key} must not only repeat its identifier"
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
                _error("INVALID_TYPE", f"{base}.config.contract", "contract must be a mapping")
            )
            return False, f"{base}.config.contract.enforced"
        canonical_enforced = canonical_contract.get("enforced", MISSING)
    legacy_enforced = MISSING
    if canonical_enforced is MISSING and legacy_contract is not MISSING:
        if not isinstance(legacy_contract, dict):
            errors.append(_error("INVALID_TYPE", f"{base}.contract", "contract must be a mapping"))
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
            errors.append(_error("INVALID_VALUE", item_path, "list item must be a nonempty string"))
            continue
        text = item.strip()
        if korean and (
            source_lint._is_placeholder_description(text)
            or not source_lint.HANGUL_RE.search(text)
        ):
            errors.append(_error("LANGUAGE_MISMATCH", item_path, "list item must be Korean prose"))
            continue
        validated.append(text)
    unique = sorted(set(validated))
    if len(unique) < minimum:
        errors.append(
            _error("INSUFFICIENT_ITEMS", path, f"at least {minimum} distinct values are required")
        )
    return unique


def _is_timestamp_data_type(value: object) -> bool:
    return isinstance(value, str) and bool(TIMESTAMP_DATA_TYPE_RE.fullmatch(value.strip()))


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


def _dependent_exposures(
    uid: str, exposures: Mapping[str, object]
) -> list[tuple[str, Mapping[str, object]]]:
    matched: list[tuple[str, Mapping[str, object]]] = []
    for exposure_uid in sorted(exposures):
        exposure = exposures[exposure_uid]
        if not isinstance(exposure, dict):
            continue
        depends_on = exposure.get("depends_on", {})
        dependency_nodes = depends_on.get("nodes", []) if isinstance(depends_on, dict) else []
        if isinstance(dependency_nodes, list) and uid in dependency_nodes:
            matched.append((exposure_uid, exposure))
    return matched


def _validated_exposure_owner(
    owner: object, path: str, errors: list[dict[str, str]]
) -> dict[str, object]:
    if not isinstance(owner, dict):
        errors.append(_error("INVALID_EXPOSURE_OWNER", path, "exposure owner must be a mapping"))
        return {"email": None, "name": None}
    name_value = owner.get("name")
    if name_value is not None and not isinstance(name_value, str):
        errors.append(_error("INVALID_EXPOSURE_OWNER", f"{path}.name", "owner name must be a string or null"))
        name: str | None = None
    else:
        name = name_value.strip() if isinstance(name_value, str) else None
        if name:
            _validate_stable_exposure_scalar(name, f"{path}.name", errors)
    email_value = owner.get("email")
    has_email = False
    if email_value is None:
        email: object = None
    elif isinstance(email_value, str):
        email = email_value.strip()
        has_email = bool(email)
        if not has_email:
            errors.append(_error("INVALID_EXPOSURE_OWNER", f"{path}.email", "owner email must be nonempty"))
        else:
            _validate_stable_exposure_scalar(email, f"{path}.email", errors)
    elif isinstance(email_value, list):
        invalid_email_item = any(
            not isinstance(item, str) or not item.strip() for item in email_value
        )
        emails = sorted(
            {
                item.strip()
                for item in email_value
                if isinstance(item, str) and item.strip()
            }
        )
        if invalid_email_item:
            errors.append(_error("INVALID_EXPOSURE_OWNER", f"{path}.email", "owner email list must contain nonempty strings"))
        email = emails
        has_email = bool(emails)
        for index, item in enumerate(email_value):
            if isinstance(item, str) and item.strip():
                _validate_stable_exposure_scalar(
                    item.strip(), f"{path}.email[{index}]", errors
                )
    else:
        errors.append(_error("INVALID_EXPOSURE_OWNER", f"{path}.email", "owner email must be string, list, or null"))
        email = None
    if not name and not has_email:
        errors.append(_error("INVALID_EXPOSURE_OWNER", path, "owner requires a nonempty name or email"))
    return {"email": email, "name": name if name is not None else None}


def _validate_stable_exposure_scalar(
    value: str, path: str, errors: list[dict[str, str]]
) -> None:
    if _absolute_filesystem_path(value):
        errors.append(
            _error(
                "ABSOLUTE_FILESYSTEM_PATH",
                path,
                "exposure catalog scalars must not contain absolute filesystem paths",
            )
        )
    elif RUNTIME_TIMESTAMP_RE.search(value):
        errors.append(
            _error(
                "DYNAMIC_TIMESTAMP_LITERAL",
                path,
                "exposure catalog scalars must not contain runtime timestamp literals",
            )
        )


def _validate_publication(
    uid: str,
    public_gold: Mapping[str, object],
    path: str,
    visibility: object,
    exposures: Mapping[str, object],
) -> tuple[list[dict[str, str]], dict[str, object], list[dict[str, object]]]:
    errors: list[dict[str, str]] = []
    projection: dict[str, object] = {}
    matched = _dependent_exposures(uid, exposures)
    exposure_status = public_gold.get("exposure_status", MISSING)
    if visibility == "published_producer":
        consumers = _validated_string_list(
            public_gold.get("intended_consumer_types", MISSING),
            f"{path}.intended_consumer_types",
            errors,
            minimum=1,
        )
        examples = _validated_string_list(
            public_gold.get("cross_domain_usage_examples", MISSING),
            f"{path}.cross_domain_usage_examples",
            errors,
            minimum=2,
            korean=True,
        )
        if exposure_status != "none_no_live_consumer":
            errors.append(_error("INVALID_EXPOSURE_STATUS", f"{path}.exposure_status", "published_producer requires none_no_live_consumer"))
        if matched:
            for exposure_uid, _ in matched:
                errors.append(_error("UNEXPECTED_EXPOSURE", f"exposures.{exposure_uid}", "published_producer must not have a live exposure"))
        projection.update(
            {
                "cross_domain_usage_examples": examples,
                "exposure_status": exposure_status if isinstance(exposure_status, str) else "",
                "intended_consumer_types": consumers,
            }
        )
    elif visibility in {"internal", "candidate"}:
        for exposure_uid, _ in matched:
            errors.append(_error("UNEXPECTED_EXPOSURE", f"exposures.{exposure_uid}", f"{visibility} models must not have exposures"))
    elif visibility == "served":
        if exposure_status != "active_exposure":
            errors.append(_error("INVALID_EXPOSURE_STATUS", f"{path}.exposure_status", "served requires active_exposure"))
        projection["exposure_status"] = exposure_status if isinstance(exposure_status, str) else ""
        if not matched:
            errors.append(_error("MISSING_ACTIVE_EXPOSURE", "exposures", "served requires a dependent manifest exposure"))

    exported_exposures: list[dict[str, object]] = []
    if visibility == "served":
        for exposure_uid, exposure in matched:
            exposure_path = f"exposures.{exposure_uid}"
            _validate_stable_exposure_scalar(exposure_uid, exposure_path, errors)
            name = _nonempty_string(exposure, "name", f"{exposure_path}.name", errors) or ""
            exposure_type = _nonempty_string(exposure, "type", f"{exposure_path}.type", errors) or ""
            if name:
                _validate_stable_exposure_scalar(name, f"{exposure_path}.name", errors)
            if exposure_type:
                _validate_stable_exposure_scalar(
                    exposure_type, f"{exposure_path}.type", errors
                )
            maturity = exposure.get("maturity")
            if maturity not in VALID_MATURITIES:
                errors.append(_error("INVALID_EXPOSURE_MATURITY", f"{exposure_path}.maturity", "exposure maturity must be low, medium, or high"))
                maturity = ""
            owner = _validated_exposure_owner(
                exposure.get("owner"), f"{exposure_path}.owner", errors
            )
            exported_exposures.append(
                {
                    "maturity": maturity,
                    "name": name,
                    "owner": owner,
                    "type": exposure_type,
                    "unique_id": exposure_uid,
                }
            )
    return errors, projection, exported_exposures


def _test_nodes_named(
    name: str, nodes: Mapping[str, object]
) -> list[tuple[str, Mapping[str, object]]]:
    return [
        (node_uid, node)
        for node_uid, node in sorted(nodes.items())
        if isinstance(node, dict)
        and node.get("resource_type") == "test"
        and node.get("name") == name
    ]


def _validate_time(
    value: object,
    path: str,
    column_names: set[str],
    column_data_types: Mapping[str, str],
    column_meta: Mapping[str, Mapping[str, object]],
    column_meta_provenance: Mapping[str, Mapping[str, str]],
    column_meta_defaults: Mapping[str, str],
    column_descriptions: Mapping[str, str],
) -> tuple[list[dict[str, str]], dict[str, object]]:
    errors: list[dict[str, str]] = []
    projection: dict[str, object] = {}
    if not isinstance(value, dict):
        return errors, projection

    canonical_timezone = _nonempty_string(
        value, "canonical_timezone", f"{path}.canonical_timezone", errors
    )
    if canonical_timezone is not None:
        projection["canonical_timezone"] = canonical_timezone
        if canonical_timezone != CANONICAL_TIMEZONE:
            errors.append(
                _error(
                    "INVALID_TIMEZONE",
                    f"{path}.canonical_timezone",
                    f"canonical_timezone must equal {CANONICAL_TIMEZONE}",
                )
            )
    for field in ("freshness_slo", "as_of_meaning", "late_repair_policy"):
        text = _korean_text(value, field, f"{path}.{field}", errors)
        if text is not None:
            projection[field] = text

    roles_value = value.get("roles", MISSING)
    if not isinstance(roles_value, dict):
        errors.append(_error("INVALID_TYPE", f"{path}.roles", "roles must be a mapping"))
        roles: Mapping[str, object] = {}
    else:
        roles = roles_value
    projected_roles: dict[str, object] = {}
    for column_name in sorted(roles, key=str):
        role_path = f"{path}.roles.{column_name}"
        role_value = roles[column_name]
        if not isinstance(column_name, str) or not isinstance(role_value, dict):
            errors.append(
                _error("INVALID_TIME_ROLE", role_path, "time roles must be named mappings")
            )
            continue
        if column_name not in column_names:
            errors.append(
                _error(
                    "UNKNOWN_TIME_COLUMN",
                    role_path,
                    "time role must name a declared model column",
                )
            )
        time_role = _nonempty_string(
            role_value, "time_role", f"{role_path}.time_role", errors
        )
        timezone = _nonempty_string(
            role_value, "timezone", f"{role_path}.timezone", errors
        )
        if timezone is not None and timezone != CANONICAL_TIMEZONE:
            errors.append(
                _error(
                    "INVALID_TIMEZONE",
                    f"{role_path}.timezone",
                    f"time role timezone must equal {CANONICAL_TIMEZONE}",
                )
            )
        projected_roles[column_name] = {
            "time_role": time_role or "",
            "timezone": timezone or "",
        }
        if column_name not in column_names:
            continue
        meta = column_meta.get(column_name, {})
        provenance = column_meta_provenance.get(column_name, {})
        default_base = column_meta_defaults.get(
            column_name, f"nodes.columns.{column_name}.config.meta"
        )
        meta_path = lambda key: provenance.get(key, f"{default_base}.{key}")
        if time_role is not None and meta.get("time_role") != time_role:
            errors.append(
                _error(
                    "TIME_ROLE_MISMATCH",
                    meta_path("time_role"),
                    "column time_role must match the public time role",
                )
            )
        if timezone is not None and meta.get("timezone") != timezone:
            errors.append(
                _error(
                    "TIMEZONE_MISMATCH",
                    meta_path("timezone"),
                    "column timezone must match the public time role",
                )
            )
    required_time_columns = {
        name for name in column_names if name.endswith("_at")
    } | {
        name
        for name, meta in column_meta.items()
        if meta.get("semantic_role") == "timestamp"
        or "time_role" in meta
        or "timezone" in meta
    } | {
        name
        for name, data_type in column_data_types.items()
        if _is_timestamp_data_type(data_type)
    } | {
        name for name in roles if name in column_names
    }
    for column_name in sorted(required_time_columns):
        meta = column_meta.get(column_name, {})
        provenance = column_meta_provenance.get(column_name, {})
        default_base = column_meta_defaults.get(
            column_name, f"nodes.columns.{column_name}.config.meta"
        )
        column_base = default_base.rsplit(".config.meta", 1)[0].rsplit(".meta", 1)[0]
        meta_path = lambda key: provenance.get(key, f"{default_base}.{key}")
        is_timestamp = _is_timestamp_data_type(column_data_types.get(column_name, ""))
        if not is_timestamp:
            errors.append(
                _error(
                    "INVALID_TIME_DATA_TYPE",
                    f"{column_base}.data_type",
                    "governed time columns require a timestamp data type",
                )
            )
        else:
            if meta.get("semantic_role") != "timestamp":
                errors.append(
                    _error(
                        "TIMESTAMP_SEMANTIC_ROLE_MISMATCH",
                        meta_path("semantic_role"),
                        "timestamp columns require semantic_role timestamp",
                    )
                )
            meta_time_role = meta.get("time_role")
            if not isinstance(meta_time_role, str) or not meta_time_role.strip():
                errors.append(
                    _error(
                        "MISSING_COLUMN_TIME_ROLE",
                        meta_path("time_role"),
                        "timestamp columns require a nonempty column time_role",
                    )
                )
            if meta.get("timezone") != CANONICAL_TIMEZONE:
                errors.append(
                    _error(
                        "INVALID_TIMEZONE",
                        meta_path("timezone"),
                        f"timestamp column timezone must equal {CANONICAL_TIMEZONE}",
                    )
                )
        if column_name not in roles:
            errors.append(
                _error(
                    "MISSING_TIME_ROLE",
                    f"{path}.roles.{column_name}",
                    "every governed time column requires a declared time role",
                )
            )
        meta_timezone = meta.get("timezone", MISSING)
        if (
            meta_timezone is not MISSING
            and meta_timezone != CANONICAL_TIMEZONE
            and column_name not in roles
        ):
            errors.append(
                _error(
                    "INVALID_TIMEZONE",
                    provenance.get("timezone", f"{default_base}.timezone"),
                    f"time-role column timezone must equal {CANONICAL_TIMEZONE}",
                )
            )
        role_value = roles.get(column_name)
        role_timezone = (
            role_value.get("timezone") if isinstance(role_value, dict) else MISSING
        )
        if (
            (meta_timezone == CANONICAL_TIMEZONE or role_timezone == CANONICAL_TIMEZONE)
            and EXPLICIT_UTC_RE.search(column_descriptions.get(column_name, ""))
        ):
            errors.append(
                _error(
                    "UTC_DESCRIPTION_CONFLICT",
                    f"{column_base}.description",
                    "Asia/Seoul time columns must not explicitly claim UTC",
                )
            )
    projection["roles"] = projected_roles
    return errors, projection


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
        errors.append(_error("INVALID_TYPE", f"{path}.enabled", "enabled must be boolean"))
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
    for field, field_name in ((canonical_key, "canonical_key"), (revision_field, "revision_field")):
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
    dependency_nodes = depends_on.get("nodes", []) if isinstance(depends_on, dict) else []
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
        or any(not isinstance(item, str) or not item.strip() for item in reconciliation_value)
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


def _validate_metrics(
    value: object,
    path: str,
    column_names: set[str],
    column_meta: Mapping[str, Mapping[str, object]],
) -> tuple[list[dict[str, str]], dict[str, object]]:
    errors: list[dict[str, str]] = []
    projection: dict[str, object] = {}
    if not isinstance(value, dict):
        return errors, projection
    metric_columns = {
        name for name, meta in column_meta.items() if meta.get("semantic_role") == "metric"
    }
    for metric_name in sorted(metric_columns - set(value)):
        errors.append(
            _error(
                "MISSING_METRIC_CONTRACT",
                f"{path}.{metric_name}",
                "every declared metric column requires a metric contract",
            )
        )
    for metric_name in sorted(value, key=str):
        metric_path = f"{path}.{metric_name}"
        metric_value = value[metric_name]
        if not isinstance(metric_name, str) or not isinstance(metric_value, dict):
            errors.append(
                _error("INVALID_METRIC", metric_path, "metric entries must be named mappings")
            )
            continue
        if metric_name not in column_names or metric_name not in metric_columns:
            errors.append(
                _error(
                    "UNKNOWN_METRIC_COLUMN",
                    metric_path,
                    "metric contract must name a declared metric column",
                )
            )
        projected_metric: dict[str, object] = {}
        expression_present = False
        for expression_field in ("expression", "formula", "source_expression"):
            if expression_field not in metric_value:
                continue
            expression = _nonempty_string(
                metric_value,
                expression_field,
                f"{metric_path}.{expression_field}",
                errors,
            )
            if expression is not None:
                expression_present = True
                projected_metric[expression_field] = expression
        if not expression_present:
            errors.append(
                _error(
                    "MISSING_METRIC_EXPRESSION",
                    f"{metric_path}.expression",
                    "metric requires an expression, formula, or source_expression",
                )
            )

        validated_scalars: dict[str, str] = {}
        for field in ("unit", "aggregation", "denominator"):
            scalar = _nonempty_string(metric_value, field, f"{metric_path}.{field}", errors)
            if scalar is not None:
                validated_scalars[field] = scalar
                projected_metric[field] = scalar
        for field in ("zero_meaning", "null_meaning"):
            text = _korean_text(metric_value, field, f"{metric_path}.{field}", errors)
            if text is not None:
                validated_scalars[field] = text
                projected_metric[field] = text
        axis_values: dict[str, list[str]] = {}
        for field in ("additive_axes", "non_additive_axes"):
            raw_axes = metric_value.get(field, MISSING)
            axes = _validated_string_list(
                raw_axes,
                f"{metric_path}.{field}",
                errors,
                minimum=0,
            )
            projected_metric[field] = axes
            axis_values[field] = axes
            if isinstance(raw_axes, list):
                seen_axes: set[str] = set()
                for index, raw_axis in enumerate(raw_axes):
                    if not isinstance(raw_axis, str) or not raw_axis.strip():
                        continue
                    axis = raw_axis.strip()
                    if axis in seen_axes:
                        errors.append(
                            _error(
                                "DUPLICATE_METRIC_AXIS",
                                f"{metric_path}.{field}[{index}]",
                                "metric axis lists must not contain duplicates",
                            )
                        )
                    seen_axes.add(axis)

        overlapping_axes = set(axis_values["additive_axes"]) & set(
            axis_values["non_additive_axes"]
        )
        raw_non_additive = metric_value.get("non_additive_axes", MISSING)
        if overlapping_axes and isinstance(raw_non_additive, list):
            for index, raw_axis in enumerate(raw_non_additive):
                if isinstance(raw_axis, str) and raw_axis.strip() in overlapping_axes:
                    errors.append(
                        _error(
                            "METRIC_AXIS_OVERLAP",
                            f"{metric_path}.non_additive_axes[{index}]",
                            "an axis cannot be both additive and non-additive",
                        )
                    )

        meta = column_meta.get(metric_name, {})
        for contract_field, meta_field in (
            ("unit", "unit"),
            ("aggregation", "aggregation_behavior"),
            ("zero_meaning", "zero_meaning"),
            ("null_meaning", "null_meaning"),
        ):
            contract_value = validated_scalars.get(contract_field)
            if contract_value is not None and meta.get(meta_field) != contract_value:
                errors.append(
                    _error(
                        "METRIC_METADATA_MISMATCH",
                        f"{metric_path}.{contract_field}",
                        f"metric {contract_field} must match column {meta_field}",
                    )
                )
        projection[metric_name] = projected_metric
    return errors, projection


def _validate_quality(
    value: object, path: str, column_names: set[str]
) -> tuple[list[dict[str, str]], dict[str, object]]:
    errors: list[dict[str, str]] = []
    projection: dict[str, object] = {}
    if not isinstance(value, dict):
        return errors, projection
    for field in (
        "completeness_explanation",
        "freshness_explanation",
        "coverage_explanation",
    ):
        text = _korean_text(value, field, f"{path}.{field}", errors)
        if text is not None:
            projection[field] = text

    state_fields_value = value.get("state_fields", MISSING)
    if not isinstance(state_fields_value, dict):
        errors.append(
            _error("INVALID_TYPE", f"{path}.state_fields", "state_fields must be a mapping")
        )
        state_fields: Mapping[str, object] = {}
    else:
        state_fields = state_fields_value
    projected_states: dict[str, object] = {}
    for column_name in sorted(state_fields, key=str):
        state_path = f"{path}.state_fields.{column_name}"
        state_value = state_fields[column_name]
        if not isinstance(column_name, str) or not isinstance(state_value, dict):
            errors.append(
                _error(
                    "INVALID_QUALITY_STATE",
                    state_path,
                    "quality state entries must be named mappings",
                )
            )
            continue
        if column_name not in column_names:
            errors.append(
                _error(
                    "UNKNOWN_QUALITY_COLUMN",
                    state_path,
                    "quality state must name a declared model column",
                )
            )
        allowed_value = state_value.get("allowed_values", MISSING)
        tokens: list[str] = []
        if (
            not isinstance(allowed_value, list)
            or not allowed_value
            or any(
                not isinstance(token, str)
                or not STABLE_ENUM_TOKEN_RE.fullmatch(token)
                for token in allowed_value
            )
            or len(set(allowed_value)) != len(allowed_value)
        ):
            errors.append(
                _error(
                    "INVALID_ENUM_TOKENS",
                    f"{state_path}.allowed_values",
                    "allowed_values must contain distinct stable lowercase enum tokens",
                )
            )
        else:
            tokens = sorted(allowed_value)

        explanations_value = state_value.get("state_explanations", MISSING)
        if not isinstance(explanations_value, dict):
            errors.append(
                _error(
                    "INVALID_TYPE",
                    f"{state_path}.state_explanations",
                    "state_explanations must be a mapping",
                )
            )
            explanations: Mapping[str, object] = {}
        else:
            explanations = explanations_value
        if set(explanations) != set(tokens):
            errors.append(
                _error(
                    "STATE_EXPLANATION_MISMATCH",
                    f"{state_path}.state_explanations",
                    "state explanations must exactly cover allowed_values",
                )
            )
        projected_explanations: dict[str, str] = {}
        for token in tokens:
            explanation = _korean_text(
                explanations,
                token,
                f"{state_path}.state_explanations.{token}",
                errors,
            )
            if explanation is not None:
                projected_explanations[token] = explanation
        projected_states[column_name] = {
            "allowed_values": tokens,
            "state_explanations": projected_explanations,
        }
    projection["state_fields"] = projected_states
    return errors, projection


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
            _error("INVALID_TYPE", f"{path}.identifiers", "identifiers must be a mapping")
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
        if not isinstance(join_name, str) or not join_name.strip() or not isinstance(join, dict):
            errors.append(_error("INVALID_JOIN", join_path, "join entries must be named mappings"))
            continue
        target = _nonempty_string(join, "target", f"{join_path}.target", errors) or ""
        source_keys_value = join.get("source_keys", MISSING)
        if (
            not isinstance(source_keys_value, list)
            or not source_keys_value
            or any(not isinstance(item, str) or not item.strip() for item in source_keys_value)
        ):
            errors.append(_error("INVALID_JOIN_SOURCE_KEYS", f"{join_path}.source_keys", "source_keys must be a nonempty ordered string list"))
            source_keys: list[str] = []
        else:
            source_keys = [item.strip() for item in source_keys_value]
            if len(set(source_keys)) != len(source_keys) or any(key not in column_names for key in source_keys):
                errors.append(_error("INVALID_JOIN_SOURCE_KEYS", f"{join_path}.source_keys", "source_keys must be unique declared model columns"))
        purpose = _korean_text(join, "purpose", f"{join_path}.purpose", errors) or ""
        cardinality = _nonempty_string(join, "cardinality", f"{join_path}.cardinality", errors) or ""
        if cardinality and cardinality not in SAFE_JOIN_CARDINALITIES:
            errors.append(_error("UNSAFE_JOIN_CARDINALITY", f"{join_path}.cardinality", "only one_to_one and many_to_one are publishable"))
        fan_out_policy = _korean_text(join, "fan_out_policy", f"{join_path}.fan_out_policy", errors) or ""
        reconciliation = _nonempty_string(
            join, "reconciliation_test", f"{join_path}.reconciliation_test", errors
        ) or ""
        if reconciliation:
            named_tests = _test_nodes_named(reconciliation, nodes)
            dependent = []
            for _, test_node in named_tests:
                depends_on = test_node.get("depends_on", {})
                dependency_nodes = depends_on.get("nodes", []) if isinstance(depends_on, dict) else []
                if isinstance(dependency_nodes, list) and uid in dependency_nodes:
                    dependent.append(test_node)
            if len(dependent) != 1:
                if not named_tests:
                    code = "RECONCILIATION_TEST_NOT_FOUND"
                elif not dependent:
                    code = "RECONCILIATION_TEST_DEPENDENCY"
                else:
                    code = "RECONCILIATION_TEST_AMBIGUOUS"
                errors.append(_error(code, f"{join_path}.reconciliation_test", "reconciliation test name must resolve uniquely to a test depending on the model"))
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
        errors.append(_error("INVALID_LIFECYCLE_STATUS", f"{path}.status", "lifecycle status must be active or deprecated"))
    else:
        projection["status"] = status
    replacement_value = value.get("replacement_relation", MISSING)
    replacement: str | None = None
    if replacement_value is not MISSING:
        replacement = _nonempty_string(value, "replacement_relation", f"{path}.replacement_relation", errors)
        if replacement is not None:
            projection["replacement_relation"] = replacement
    future_value = value.get("replacement_is_future", MISSING)
    if future_value is not MISSING:
        if not isinstance(future_value, bool):
            errors.append(_error("INVALID_TYPE", f"{path}.replacement_is_future", "replacement_is_future must be boolean"))
        else:
            projection["replacement_is_future"] = future_value
    if status == "deprecated":
        if replacement is None:
            errors.append(_error("MISSING_REPLACEMENT", f"{path}.replacement_relation", "deprecated requires a replacement relation"))
        guidance = _korean_text(
            value,
            "compatibility_window_guidance",
            f"{path}.compatibility_window_guidance",
            errors,
        )
        if guidance is not None:
            projection["compatibility_window_guidance"] = guidance
    elif status == "active" and replacement is not None and future_value is not True:
        errors.append(_error("UNMARKED_FUTURE_REPLACEMENT", f"{path}.replacement_is_future", "active replacement must be explicitly marked future"))
    return errors, projection


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
    description = _korean_text(
        node, "description", f"{base}.description", errors, identifier=name
    ) or ""
    declared_uid = node.get("unique_id", uid)
    if declared_uid != uid:
        errors.append(
            _error("UNIQUE_ID_MISMATCH", f"{base}.unique_id", "node unique_id must match its mapping key")
        )

    _nonempty_string(public_gold, "contract_version", f"{public_gold_path}.contract_version", errors)
    language = _nonempty_string(
        public_gold, "documentation_language", f"{public_gold_path}.documentation_language", errors
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
            _error("INVALID_VALUE", f"{public_gold_path}.maturity", "maturity must be low, medium, or high")
        )
    visibility = public_gold.get("visibility")
    if visibility not in VALID_VISIBILITIES:
        errors.append(
            _error("INVALID_VALUE", f"{public_gold_path}.visibility", "visibility is not supported")
        )
        visibility = None
    contract_status = public_gold.get("contract_status")
    if contract_status not in VALID_CONTRACT_STATUSES:
        errors.append(
            _error("INVALID_VALUE", f"{public_gold_path}.contract_status", "contract_status is not supported")
        )
        contract_status = None
    for field in STRUCTURED_FIELDS:
        if not isinstance(public_gold.get(field), dict):
            errors.append(
                _error("INVALID_TYPE", f"{public_gold_path}.{field}", f"{field} must be a mapping")
            )
    errors.extend(_unsafe_contract_errors(public_gold, public_gold_path))

    primary_key_value = public_gold.get("primary_key")
    primary_keys: list[str] = []
    if (
        not isinstance(primary_key_value, list)
        or not primary_key_value
        or any(not isinstance(item, str) or not item.strip() for item in primary_key_value)
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
                _error("INVALID_PRIMARY_KEY", f"{public_gold_path}.primary_key", "primary_key names must be unique")
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
        errors.append(_error("INVALID_TYPE", f"{base}.columns", "columns must be a mapping"))
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
            errors.append(_error("INVALID_TYPE", column_base, "column entries must be named mappings"))
            continue
        declared_name = column_value.get("name", column_name)
        if declared_name != column_name:
            errors.append(
                _error("COLUMN_NAME_MISMATCH", f"{column_base}.name", "column.name must match its mapping key")
            )
        column_description = _korean_text(
            column_value,
            "description",
            f"{column_base}.description",
            errors,
            identifier=column_name,
        ) or ""
        data_type = _nonempty_string(
            column_value, "data_type", f"{column_base}.data_type", errors
        ) or ""
        column_data_types_by_name[column_name] = data_type
        meta, meta_provenance, meta_default_base, meta_errors = _column_meta(
            column_value, column_base
        )
        errors.extend(meta_errors)
        column_meta_by_name[column_name] = meta
        column_meta_provenance_by_name[column_name] = meta_provenance
        column_meta_defaults_by_name[column_name] = meta_default_base
        column_descriptions_by_name[column_name] = column_description
        meta_path = lambda key: meta_provenance.get(key, f"{meta_default_base}.{key}")
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

    publication_errors, publication_projection, exposure_projection = _validate_publication(
        uid, public_gold, public_gold_path, visibility, exposures
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
    if not isinstance(depends_on, dict) or not isinstance(depends_on.get("nodes", []), list):
        errors.append(
            _error("INVALID_TYPE", f"{base}.depends_on.nodes", "direct dependencies must be a list")
        )
    else:
        dependency_values = depends_on.get("nodes", [])
        if any(not isinstance(item, str) or not item for item in dependency_values):
            errors.append(
                _error("INVALID_TYPE", f"{base}.depends_on.nodes", "dependency IDs must be nonempty strings")
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


def validate_manifest(
    manifest: object,
    resources: Iterable[str] | None = None,
    required_language: str = "ko-KR",
) -> tuple[dict[str, object], dict[str, object] | None]:
    """Validate manifest declarations and return ``(report, catalog-or-None)``."""
    if required_language != "ko-KR":
        error = _error("UNSUPPORTED_LANGUAGE", "required_language", "only ko-KR is supported")
        return _report(
            "ERROR", [error], declared_status="FAIL", required_language=required_language
        ), None
    try:
        _preflight_json(manifest)
        root = _artifact_mapping(manifest, "manifest")
        metadata = _artifact_mapping(root.get("metadata"), "metadata")
        schema_version = metadata.get("dbt_schema_version")
        if not isinstance(schema_version, str) or not schema_version.endswith(MANIFEST_V12_SUFFIX):
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
                    "INVALID_ARTIFACT_SHAPE", "nodes", "node keys and values must be string/mapping pairs"
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
            "ERROR", [detail], declared_status="FAIL", required_language=required_language
        ), None

    governed: dict[str, tuple[Mapping[str, object], dict[str, object], str, list[dict[str, str]]]] = {}
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
                    _error("RESOURCE_NOT_FOUND", f"resources.{selector}", "resource selector did not resolve")
                )
            elif len(matches) > 1:
                selector_errors.append(
                    _error("RESOURCE_AMBIGUOUS", f"resources.{selector}", "resource selector is ambiguous")
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


def _argument_parser() -> argparse.ArgumentParser:
    parser = ReportArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="dbt manifest v12 JSON path")
    parser.add_argument("--resource", action="append", help="model name or unique ID")
    parser.add_argument("--require-language", required=True, help="required documentation language")
    parser.add_argument("--output", help="write catalog JSON after validation PASS")
    return parser


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON constant is unsupported: {value}")


def _load_manifest(path: Path) -> object:
    if path.is_symlink() or not path.is_file():
        raise OSError("manifest must be an existing regular non-symlink file")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle, parse_constant=_reject_json_constant)


def _validated_output_path(output: Path, manifest: Path) -> Path:
    requested = output.expanduser().absolute()
    if requested.is_symlink():
        raise OSError("output symlinks are unsupported")
    if not requested.parent.is_dir():
        raise OSError("output parent must be an existing directory")
    if requested.exists() and not requested.is_file():
        raise OSError("output must be a regular file")
    manifest_resolved = manifest.resolve(strict=True)
    if requested.exists() and os.path.samefile(requested, manifest):
        raise OSError("output must not overwrite the manifest")
    canonical = (
        requested.resolve(strict=True)
        if requested.exists()
        else requested.parent.resolve(strict=True) / requested.name
    )
    if canonical == manifest_resolved:
        raise OSError("output must not overwrite the manifest")
    return canonical


def _atomic_write(path: Path, value: str) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = _argument_parser().parse_args(argv)
    except CliArgumentError as error:
        report = _report(
            "ERROR",
            [_error("CLI_ERROR", "cli", str(error))],
            declared_status="FAIL",
            required_language="",
        )
        write_utf8_stdout(render_json(report))
        return 2

    manifest_path = Path(arguments.manifest).expanduser().absolute()
    try:
        manifest = _load_manifest(manifest_path)
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        report = _report(
            "ERROR",
            [_error("MANIFEST_READ_ERROR", "manifest", f"cannot read manifest JSON: {error}")],
            declared_status="FAIL",
            required_language=arguments.require_language,
        )
        write_utf8_stdout(render_json(report))
        return 2

    report, catalog = validate_manifest(
        manifest,
        resources=arguments.resource,
        required_language=arguments.require_language,
    )
    if report["status"] == "PASS" and arguments.output:
        try:
            output = _validated_output_path(Path(arguments.output), manifest_path)
            if catalog is None:
                raise OSError("catalog was not produced")
            _atomic_write(output, render_json(catalog))
        except (OSError, UnicodeError) as error:
            report = _report(
                "ERROR",
                [_error("OUTPUT_WRITE_ERROR", "output", f"cannot write catalog: {error}")],
                declared_status=str(report["proof"]["declared_contract"]),
                required_language=arguments.require_language,
                resources=report.get("resources", []),
            )
    write_utf8_stdout(render_json(report))
    return {"PASS": 0, "FAIL": 1, "ERROR": 2}[str(report["status"])]


if __name__ == "__main__":
    raise SystemExit(main())
