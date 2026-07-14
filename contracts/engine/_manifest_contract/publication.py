"""Internal _manifest_contract publication responsibility."""

from __future__ import annotations

from typing import Mapping

from .foundation import (
    MISSING,
    RUNTIME_TIMESTAMP_RE,
    VALID_MATURITIES,
    _absolute_filesystem_path,
    _error,
)

from .metadata import (
    _nonempty_string,
    _validated_string_list,
)


def _dependent_exposures(
    uid: str, exposures: Mapping[str, object]
) -> list[tuple[str, Mapping[str, object]]]:
    matched: list[tuple[str, Mapping[str, object]]] = []
    for exposure_uid in sorted(exposures):
        exposure = exposures[exposure_uid]
        if not isinstance(exposure, dict):
            continue
        depends_on = exposure.get("depends_on", {})
        dependency_nodes = (
            depends_on.get("nodes", []) if isinstance(depends_on, dict) else []
        )
        if isinstance(dependency_nodes, list) and uid in dependency_nodes:
            matched.append((exposure_uid, exposure))
    return matched


def _validated_exposure_owner(
    owner: object, path: str, errors: list[dict[str, str]]
) -> dict[str, object]:
    if not isinstance(owner, dict):
        errors.append(
            _error("INVALID_EXPOSURE_OWNER", path, "exposure owner must be a mapping")
        )
        return {"email": None, "name": None}
    name_value = owner.get("name")
    if name_value is not None and not isinstance(name_value, str):
        errors.append(
            _error(
                "INVALID_EXPOSURE_OWNER",
                f"{path}.name",
                "owner name must be a string or null",
            )
        )
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
            errors.append(
                _error(
                    "INVALID_EXPOSURE_OWNER",
                    f"{path}.email",
                    "owner email must be nonempty",
                )
            )
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
            errors.append(
                _error(
                    "INVALID_EXPOSURE_OWNER",
                    f"{path}.email",
                    "owner email list must contain nonempty strings",
                )
            )
        email = emails
        has_email = bool(emails)
        for index, item in enumerate(email_value):
            if isinstance(item, str) and item.strip():
                _validate_stable_exposure_scalar(
                    item.strip(), f"{path}.email[{index}]", errors
                )
    else:
        errors.append(
            _error(
                "INVALID_EXPOSURE_OWNER",
                f"{path}.email",
                "owner email must be string, list, or null",
            )
        )
        email = None
    if not name and not has_email:
        errors.append(
            _error(
                "INVALID_EXPOSURE_OWNER",
                path,
                "owner requires a nonempty name or email",
            )
        )
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
            errors.append(
                _error(
                    "INVALID_EXPOSURE_STATUS",
                    f"{path}.exposure_status",
                    "published_producer requires none_no_live_consumer",
                )
            )
        if matched:
            for exposure_uid, _ in matched:
                errors.append(
                    _error(
                        "UNEXPECTED_EXPOSURE",
                        f"exposures.{exposure_uid}",
                        "published_producer must not have a live exposure",
                    )
                )
        projection.update(
            {
                "cross_domain_usage_examples": examples,
                "exposure_status": exposure_status
                if isinstance(exposure_status, str)
                else "",
                "intended_consumer_types": consumers,
            }
        )
    elif visibility in {"internal", "candidate"}:
        for exposure_uid, _ in matched:
            errors.append(
                _error(
                    "UNEXPECTED_EXPOSURE",
                    f"exposures.{exposure_uid}",
                    f"{visibility} models must not have exposures",
                )
            )
    elif visibility == "served":
        if exposure_status != "active_exposure":
            errors.append(
                _error(
                    "INVALID_EXPOSURE_STATUS",
                    f"{path}.exposure_status",
                    "served requires active_exposure",
                )
            )
        projection["exposure_status"] = (
            exposure_status if isinstance(exposure_status, str) else ""
        )
        if not matched:
            errors.append(
                _error(
                    "MISSING_ACTIVE_EXPOSURE",
                    "exposures",
                    "served requires a dependent manifest exposure",
                )
            )

    exported_exposures: list[dict[str, object]] = []
    if visibility == "served":
        for exposure_uid, exposure in matched:
            exposure_path = f"exposures.{exposure_uid}"
            _validate_stable_exposure_scalar(exposure_uid, exposure_path, errors)
            name = (
                _nonempty_string(exposure, "name", f"{exposure_path}.name", errors)
                or ""
            )
            exposure_type = (
                _nonempty_string(exposure, "type", f"{exposure_path}.type", errors)
                or ""
            )
            if name:
                _validate_stable_exposure_scalar(name, f"{exposure_path}.name", errors)
            if exposure_type:
                _validate_stable_exposure_scalar(
                    exposure_type, f"{exposure_path}.type", errors
                )
            maturity = exposure.get("maturity")
            if maturity not in VALID_MATURITIES:
                errors.append(
                    _error(
                        "INVALID_EXPOSURE_MATURITY",
                        f"{exposure_path}.maturity",
                        "exposure maturity must be low, medium, or high",
                    )
                )
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
