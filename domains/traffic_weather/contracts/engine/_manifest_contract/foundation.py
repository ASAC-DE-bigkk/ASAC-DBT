"""Internal _manifest_contract foundation responsibility."""

from __future__ import annotations

import json
import math
import re
from typing import Iterable

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


STRUCTURED_FIELDS = (
    "time",
    "space",
    "metrics",
    "joins",
    "quality",
    "lineage",
    "lifecycle",
)


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


SAFE_KEY_ROLES = {
    "key",
    "primary_key",
    "join_key",
    "dimension_key",
    "foreign_key",
    "identifier",
}


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


EXPLICIT_UTC_RE = re.compile(r"(?<![A-Za-z0-9_])UTC(?![A-Za-z0-9_])", re.IGNORECASE)


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
        marker in compact for marker in ("credential", "token", "secret", "password")
    ):
        return True
    if any(marker in compact for marker in ("accesskey", "privatekey", "apikey")):
        return True
    return "path" in tokens or compact.endswith("path")


def _absolute_filesystem_path(value: str) -> bool:
    return value.startswith(("/", "\\\\")) or bool(
        re.match(r"^[A-Za-z]:[\\\\/]", value)
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
        key=lambda item: (
            item.get("path", ""),
            item.get("code", ""),
            item.get("message", ""),
        ),
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
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    )
