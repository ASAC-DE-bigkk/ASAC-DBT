"""Internal _schema_contract reporting responsibility."""

from __future__ import annotations

import json
from typing import Iterable

from .types import CLAIM_LIMITATIONS_KO


def _error_sort_key(error: dict[str, object]) -> tuple[object, ...]:
    lines = error.get("lines")
    line = lines[0] if isinstance(lines, list) and lines else error.get("line", 0)
    files = error.get("files")
    file_name = (
        files[0]
        if isinstance(files, list) and files
        else error.get("file", error.get("path", ""))
    )
    return (
        file_name,
        line,
        error.get("code", ""),
        error.get("resource_name", ""),
        error.get("column", ""),
    )


def _proof_fields(
    *, status: str, errors: Iterable[dict[str, object]], files_complete: bool
) -> dict[str, object]:
    error_codes = {str(error.get("code", "")) for error in errors}
    uniqueness_pass = (
        status != "ERROR"
        and files_complete
        and not {
            "DUPLICATE_COLUMN",
            "DUPLICATE_RESOURCE",
            "MISSING_COLUMN_NAME",
            "MISSING_RESOURCE_NAME",
        }
        & error_codes
    )
    return {
        "claim_limitations_ko": CLAIM_LIMITATIONS_KO,
        "proof": {
            "data_contract": "NOT_RUN",
            "declared_contract": "PASS" if status == "PASS" else "FAIL",
            "manual_semantic_review": "REQUIRED",
            "physical_contract": "NOT_RUN",
            "source_yaml_uniqueness": "PASS" if uniqueness_pass else "FAIL",
        },
        "proof_scope": "source_yaml_declaration",
    }


def _empty_report(status: str, errors: list[dict[str, object]]) -> dict[str, object]:
    report: dict[str, object] = {
        "descriptions": [],
        "errors": sorted(errors, key=_error_sort_key),
        "files": [],
        "required_language": "ko-KR",
        "resources": [],
        "status": status,
        "summary": {
            "coverage_percentage": 0.0,
            "description_fields_accounted": 0,
            "description_fields_expected": 0,
            "description_fields_present": 0,
            "description_fields_unaccounted": 0,
            "error_count": len(errors),
            "files_scanned": 0,
            "files_total": 0,
            "resources_scanned": 0,
            "resources_total": 0,
            "resources_unaccounted": 0,
        },
    }
    report.update(_proof_fields(status=status, errors=errors, files_complete=False))
    return report


def render_report(report: dict[str, object]) -> str:
    return json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
