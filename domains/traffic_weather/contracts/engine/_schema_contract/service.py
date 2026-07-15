"""Internal _schema_contract service responsibility."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from .parsing import _parse_yaml_subset

from .reporting import (
    _empty_report,
    _error_sort_key,
    _proof_fields,
)

from .repository import (
    _cross_file_duplicate_errors,
    _discover_files,
    _nearest_project_scope,
)

from .resources import _extract_resources

from .types import (
    MAX_FILE_BYTES,
    ScanError,
)


def lint_schema_contracts(
    schema_roots: Iterable[str | Path],
    resources: Iterable[str] | None = None,
    required_language: str = "ko-KR",
) -> dict[str, object]:
    """Lint discovered dbt schema YAML and return a deterministic audit report."""
    if required_language != "ko-KR":
        report = _empty_report(
            "ERROR",
            [
                {
                    "code": "UNSUPPORTED_LANGUAGE",
                    "message": f"unsupported required language: {required_language}",
                }
            ],
        )
        report["required_language"] = required_language
        return report

    paths, input_errors = _discover_files(schema_roots)
    if input_errors:
        return _empty_report("ERROR", input_errors)

    fallback_scope = Path(
        os.path.commonpath([path.parent.as_posix() for path in paths])
    ).resolve()

    selected = set(resources) if resources is not None else None
    if selected == set():
        selected = None
    file_reports: list[dict[str, object]] = []
    all_resources: list[dict[str, object]] = []
    all_descriptions: list[dict[str, object]] = []
    all_errors: list[dict[str, object]] = []
    discovered_names: set[str] = set()
    io_error = False

    for path in paths:
        path_string = path.as_posix()
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                raise ScanError(
                    f"file exceeds maximum size of {MAX_FILE_BYTES} bytes",
                    code="INPUT_LIMIT_EXCEEDED",
                )
            text = path.read_text(encoding="utf-8")
            root = _parse_yaml_subset(text)
            file_resources, descriptions, errors, discovered = _extract_resources(
                root, path_string, selected
            )
        except (OSError, UnicodeError) as error:
            io_error = True
            detail = {
                "code": "IO_ERROR",
                "file": path_string,
                "message": f"cannot read UTF-8 YAML: {error}",
            }
            all_errors.append(detail)
            file_reports.append(
                {
                    "error_codes": ["IO_ERROR"],
                    "path": path_string,
                    "resource_names": [],
                    "scan_status": "FAIL",
                }
            )
            continue
        except ScanError as error:
            detail: dict[str, object] = {
                "code": error.code,
                "file": path_string,
                "message": error.message,
            }
            if error.line is not None:
                detail["line"] = error.line
            if error.lines is not None:
                detail["lines"] = error.lines
            if error.key is not None:
                detail["key"] = error.key
            all_errors.append(detail)
            file_reports.append(
                {
                    "error_codes": [error.code],
                    "path": path_string,
                    "resource_names": [],
                    "scan_status": "FAIL",
                }
            )
            continue

        project_scope = _nearest_project_scope(path, fallback_scope)
        for resource in file_resources:
            resource["project_scope"] = project_scope
        discovered_names.update(discovered)
        all_resources.extend(file_resources)
        all_descriptions.extend(descriptions)
        all_errors.extend(errors)
        file_reports.append(
            {
                "error_codes": sorted({error["code"] for error in errors}),
                "path": path_string,
                "resource_names": [resource["name"] for resource in file_resources],
                "scan_status": "PASS",
            }
        )

    all_errors.extend(_cross_file_duplicate_errors(all_resources))

    if selected is not None:
        for missing in sorted(selected - discovered_names):
            all_errors.append(
                {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"selected resource was not discovered: {missing}",
                    "resource_name": missing,
                }
            )

        for selector in sorted(selected & discovered_names):
            project_scopes = sorted(
                {
                    str(resource["project_scope"])
                    for resource in all_resources
                    if resource["name"] == selector
                }
            )
            if len(project_scopes) > 1:
                all_errors.append(
                    {
                        "code": "RESOURCE_SELECTOR_AMBIGUOUS",
                        "message": (
                            f"selected resource exists in multiple dbt projects: {selector}"
                        ),
                        "project_scopes": project_scopes,
                        "resource_name": selector,
                    }
                )

    all_errors.sort(key=_error_sort_key)
    resources_unaccounted = sum(
        error["code"] in {"MISSING_RESOURCE_NAME", "RESOURCE_NOT_FOUND"}
        for error in all_errors
    )
    descriptions_unaccounted = sum(
        error["code"]
        in {"MISSING_COLUMN_NAME", "MISSING_RESOURCE_NAME", "RESOURCE_NOT_FOUND"}
        for error in all_errors
    )
    descriptions_expected = len(all_descriptions) + descriptions_unaccounted
    descriptions_accounted = sum(bool(item["accounted"]) for item in all_descriptions)
    files_scanned = sum(item["scan_status"] == "PASS" for item in file_reports)
    resources_scanned = len(all_resources)
    resources_total = len(all_resources) + resources_unaccounted
    denominator = len(file_reports) + resources_total + descriptions_expected
    numerator = files_scanned + resources_scanned + descriptions_accounted
    coverage = round(100.0 * numerator / denominator, 2) if denominator else 0.0
    status = "ERROR" if io_error else ("FAIL" if all_errors else "PASS")
    report: dict[str, object] = {
        "descriptions": all_descriptions,
        "errors": all_errors,
        "files": file_reports,
        "required_language": required_language,
        "resources": all_resources,
        "status": status,
        "summary": {
            "coverage_percentage": coverage,
            "description_fields_accounted": descriptions_accounted,
            "description_fields_expected": descriptions_expected,
            "description_fields_present": sum(
                bool(item["present"]) for item in all_descriptions
            ),
            "description_fields_unaccounted": descriptions_unaccounted,
            "error_count": len(all_errors),
            "files_scanned": files_scanned,
            "files_total": len(file_reports),
            "resources_scanned": resources_scanned,
            "resources_total": resources_total,
            "resources_unaccounted": resources_unaccounted,
        },
    }
    report.update(
        _proof_fields(
            status=status,
            errors=all_errors,
            files_complete=files_scanned == len(file_reports),
        )
    )
    return report
