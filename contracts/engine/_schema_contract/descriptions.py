"""Internal _schema_contract descriptions responsibility."""

from __future__ import annotations

import re
import unicodedata

from .types import (
    HANGUL_RE,
    MapEntry,
    PLACEHOLDER_RE,
    ScanError,
)


def _scalar(entry: MapEntry | None, *, context: str) -> str | None:
    if entry is None:
        return None
    if entry.value.kind != "scalar":
        raise ScanError(f"{context} must be a scalar", line=entry.line)
    return entry.value.value or ""


def _normal_identifier(value: str) -> str:
    return "".join(
        character.casefold()
        for character in unicodedata.normalize("NFKC", value)
        if character.isalnum()
    )


PLACEHOLDER_WRAPPERS = (
    ("**", "**"),
    ("__", "__"),
    ("(", ")"),
    ("【", "】"),
    ("「", "」"),
    ("『", "』"),
    ("`", "`"),
    ("'", "'"),
    ('"', '"'),
    ("“", "”"),
    ("‘", "’"),
)


PLACEHOLDER_WRAPPER_SUFFIXES = ("입니다", "이다", "임", "예정", "")


def _unwrap_placeholder_grammar(value: str) -> str:
    for suffix in PLACEHOLDER_WRAPPER_SUFFIXES:
        if suffix and not value.endswith(suffix):
            continue
        core = value[: -len(suffix)].strip() if suffix else value.strip()
        changed = False
        while True:
            for opening, closing in PLACEHOLDER_WRAPPERS:
                if core.startswith(opening) and core.endswith(closing):
                    core = core[len(opening) : -len(closing)].strip()
                    changed = True
                    break
            else:
                break
        if changed:
            return f"{core}{suffix}"
    return value


def _is_single_placeholder(value: str) -> bool:
    without_terminal = value.strip().rstrip(".!?。！？")
    return bool(PLACEHOLDER_RE.fullmatch(_unwrap_placeholder_grammar(without_terminal)))


def _is_placeholder_description(value: str) -> bool:
    normalized = unicodedata.normalize("NFKC", value).strip()
    if _is_single_placeholder(normalized):
        return True
    segments = re.split(r"\s*(?:/|:|[-–—·])\s*", normalized)
    return len(segments) > 1 and all(
        segment and _is_single_placeholder(segment) for segment in segments
    )


def _description_evidence(
    *,
    path: str,
    resource_kind: str,
    resource_name: str,
    entity_kind: str,
    identifier: str,
    description: MapEntry | None,
    entity_line: int,
    column: str | None = None,
) -> tuple[dict[str, object], dict[str, object] | None]:
    evidence: dict[str, object] = {
        "accounted": True,
        "entity_kind": entity_kind,
        "expected": True,
        "field": "description",
        "file": path,
        "language_status": "MISSING",
        "present": description is not None,
        "resource_kind": resource_kind,
        "resource_name": resource_name,
        "scanned": True,
    }
    if column is not None:
        evidence["column"] = column
    if description is None:
        error = {
            "code": "MISSING_DESCRIPTION",
            "entity_kind": entity_kind,
            "field": "description",
            "file": path,
            "line": entity_line,
            "message": f"missing description for {entity_kind} '{identifier}'",
            "resource_kind": resource_kind,
            "resource_name": resource_name,
        }
        if column is not None:
            error["column"] = column
        return evidence, error
    if description.value.kind != "scalar":
        raise ScanError("description must be a scalar", line=description.line)
    value = description.value.value or ""
    evidence["line"] = description.line
    evidence["language_status"] = "PASS"
    evidence["value"] = value

    code: str | None = None
    reason: str | None = None
    if _is_placeholder_description(value):
        code, reason = "PLACEHOLDER_DESCRIPTION", "description is a placeholder"
        evidence["language_status"] = "PLACEHOLDER"
    elif _normal_identifier(value) == _normal_identifier(identifier):
        code, reason = (
            "IDENTIFIER_ONLY_DESCRIPTION",
            "description only repeats its identifier",
        )
        evidence["language_status"] = "IDENTIFIER_ONLY"
    elif not HANGUL_RE.search(value):
        code, reason = "DESCRIPTION_LANGUAGE", "description does not contain Hangul"
        evidence["language_status"] = "MISSING_HANGUL"
    if code is None:
        return evidence, None
    error = {
        "code": code,
        "entity_kind": entity_kind,
        "field": "description",
        "file": path,
        "line": description.line,
        "message": reason,
        "resource_kind": resource_kind,
        "resource_name": resource_name,
    }
    if column is not None:
        error["column"] = column
    return evidence, error
