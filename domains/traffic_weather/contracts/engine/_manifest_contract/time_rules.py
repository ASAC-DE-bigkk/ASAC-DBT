"""Internal _manifest_contract time_rules responsibility."""

from __future__ import annotations

from typing import Mapping

from .foundation import (
    CANONICAL_TIMEZONE,
    EXPLICIT_UTC_RE,
    MISSING,
    _error,
)

from .metadata import (
    _is_timestamp_data_type,
    _korean_text,
    _nonempty_string,
)


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
        errors.append(
            _error("INVALID_TYPE", f"{path}.roles", "roles must be a mapping")
        )
        roles: Mapping[str, object] = {}
    else:
        roles = roles_value
    projected_roles: dict[str, object] = {}
    for column_name in sorted(roles, key=str):
        role_path = f"{path}.roles.{column_name}"
        role_value = roles[column_name]
        if not isinstance(column_name, str) or not isinstance(role_value, dict):
            errors.append(
                _error(
                    "INVALID_TIME_ROLE", role_path, "time roles must be named mappings"
                )
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

        def meta_path(key: str) -> str:
            return provenance.get(key, f"{default_base}.{key}")

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
    required_time_columns = (
        {name for name in column_names if name.endswith("_at")}
        | {
            name
            for name, meta in column_meta.items()
            if meta.get("semantic_role") == "timestamp"
            or "time_role" in meta
            or "timezone" in meta
        }
        | {
            name
            for name, data_type in column_data_types.items()
            if _is_timestamp_data_type(data_type)
        }
        | {name for name in roles if name in column_names}
    )
    for column_name in sorted(required_time_columns):
        meta = column_meta.get(column_name, {})
        provenance = column_meta_provenance.get(column_name, {})
        default_base = column_meta_defaults.get(
            column_name, f"nodes.columns.{column_name}.config.meta"
        )
        column_base = default_base.rsplit(".config.meta", 1)[0].rsplit(".meta", 1)[0]

        def meta_path(key: str) -> str:
            return provenance.get(key, f"{default_base}.{key}")

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
            meta_timezone == CANONICAL_TIMEZONE or role_timezone == CANONICAL_TIMEZONE
        ) and EXPLICIT_UTC_RE.search(column_descriptions.get(column_name, "")):
            errors.append(
                _error(
                    "UTC_DESCRIPTION_CONFLICT",
                    f"{column_base}.description",
                    "Asia/Seoul time columns must not explicitly claim UTC",
                )
            )
    projection["roles"] = projected_roles
    return errors, projection
