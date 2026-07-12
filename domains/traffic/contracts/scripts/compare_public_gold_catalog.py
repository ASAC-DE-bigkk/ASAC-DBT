#!/usr/bin/env python3
"""Compare validated public-Gold declarations with a supplied dbt catalog."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Iterable, Mapping, Sequence

try:
    from domains.traffic.contracts.scripts.artifact_io import write_utf8_stdout
except ModuleNotFoundError:  # Direct execution from scripts/contracts.
    from artifact_io import write_utf8_stdout

try:
    from domains.traffic.contracts.scripts import validate_public_gold_manifest as manifest_validator
except ModuleNotFoundError:  # Direct execution from scripts/contracts.
    import validate_public_gold_manifest as manifest_validator


CATALOG_V1_SUFFIX = "/dbt/catalog/v1.json"
EVIDENCE_KINDS = {"fixture", "approved_dev_catalog"}
EVIDENCE_SCOPES = {
    "approved_dev_catalog": "operator_asserted_approved_dev_catalog",
    "fixture": "non_dev_fixture",
}
EVIDENCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
CLAIM_LIMITATIONS_KO = (
    "이 검사는 제공된 dbt catalog 아티팩트의 물리 컬럼·타입·순서를 선언과 비교할 뿐, "
    "승인 또는 dev warehouse 실행을 암호학적으로 확인하지 않습니다. catalog 주석, "
    "SQL projection, grain, 최신 행 선택, reconciliation, 데이터 값 또는 의미적 진실성도 "
    "증명하지 않습니다."
)
MISSING = object()


class CliArgumentError(Exception):
    pass


class ReportArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliArgumentError(message)


def _error(code: str, path: str, message: str, **details: object) -> dict[str, object]:
    result: dict[str, object] = {"code": code, "message": message, "path": path}
    result.update(details)
    return result


def _evidence(evidence_kind: str, evidence_id: str | None) -> dict[str, object]:
    return {
        "attestation": "operator_supplied_unverified",
        "evidence_id": evidence_id,
        "evidence_kind": evidence_kind,
        "evidence_scope": EVIDENCE_SCOPES.get(
            evidence_kind, "invalid_evidence_kind"
        ),
    }


def _validate_evidence_argument(
    evidence_kind: str, evidence_id: object
) -> tuple[str | None, dict[str, object] | None]:
    normalized_evidence_id = evidence_id if isinstance(evidence_id, str) else None
    if evidence_kind not in EVIDENCE_KINDS:
        return None, _error("CLI_ERROR", "evidence_kind", "unsupported evidence kind")
    if evidence_kind == "approved_dev_catalog" and not normalized_evidence_id:
        return None, _error(
            "MISSING_EVIDENCE_ID",
            "evidence_id",
            "approved_dev_catalog requires a nonempty evidence ID",
        )
    if normalized_evidence_id is not None and not EVIDENCE_ID_RE.fullmatch(
        normalized_evidence_id
    ):
        return None, _error(
            "INVALID_EVIDENCE_ID",
            "evidence_id",
            "evidence ID must match ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
        )
    return normalized_evidence_id, None


def _proof(
    declared_status: str,
    comparison_status: str,
    evidence_kind: str,
    evidence_id: str | None,
) -> dict[str, str]:
    physical_status = "NOT_RUN"
    if (
        declared_status == "PASS"
        and comparison_status in {"PASS", "FAIL"}
        and evidence_kind == "approved_dev_catalog"
        and evidence_id
    ):
        physical_status = comparison_status
    return {
        "catalog_comparison": comparison_status,
        "data_contract": "NOT_RUN",
        "declared_contract": declared_status,
        "manual_semantic_review": "REQUIRED",
        "physical_contract": physical_status,
        "source_yaml_uniqueness": "NOT_RUN",
    }


def _report(
    status: str,
    errors: Iterable[dict[str, object]],
    *,
    declared_status: str,
    comparison_status: str,
    evidence_kind: str,
    evidence_id: str | None,
    required_language: str,
    resources: Iterable[str] = (),
) -> dict[str, object]:
    ordered_errors = sorted(
        errors,
        key=lambda item: (
            str(item.get("path", "")),
            str(item.get("code", "")),
            str(item.get("column", "")),
            str(item.get("message", "")),
        ),
    )
    selected_resources = sorted(set(resources))
    return {
        "claim_limitations_ko": CLAIM_LIMITATIONS_KO,
        "errors": ordered_errors,
        "evidence": _evidence(evidence_kind, evidence_id),
        "proof": _proof(
            declared_status, comparison_status, evidence_kind, evidence_id
        ),
        "proof_scope": "supplied_dbt_catalog_artifact_comparison",
        "required_language": required_language,
        "resources": selected_resources,
        "status": status,
        "summary": {
            "difference_count": (
                len(ordered_errors) if comparison_status == "FAIL" else 0
            ),
            "error_count": len(ordered_errors) if status == "ERROR" else 0,
            "resources_checked": (
                len(selected_resources)
                if comparison_status in {"PASS", "FAIL"}
                else 0
            ),
        },
    }


def _with_output_error(
    report: dict[str, object], output_error: dict[str, object]
) -> dict[str, object]:
    updated = dict(report)
    updated["errors"] = [*report.get("errors", []), output_error]
    summary = dict(report.get("summary", {}))
    summary["error_count"] = int(summary.get("error_count", 0)) + 1
    updated["summary"] = summary
    updated["status"] = "ERROR"
    return updated


def render_json(value: object) -> str:
    return manifest_validator.render_json(value)


def _mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise manifest_validator.ArtifactShapeError(
            "INVALID_ARTIFACT_SHAPE", path, f"{path} must be a mapping"
        )
    return value


def _nonempty_string(value: object, code: str, path: str, message: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise manifest_validator.ArtifactShapeError(code, path, message)
    return value


def _validated_catalog(catalog: object) -> tuple[Mapping[str, object], Mapping[str, object]]:
    manifest_validator._preflight_json(catalog, "catalog")
    root = _mapping(catalog, "catalog")
    metadata = _mapping(root.get("metadata"), "catalog.metadata")
    schema_version = metadata.get("dbt_schema_version")
    if not isinstance(schema_version, str) or not schema_version.endswith(
        CATALOG_V1_SUFFIX
    ):
        raise manifest_validator.ArtifactShapeError(
            "UNSUPPORTED_CATALOG_VERSION",
            "catalog.metadata.dbt_schema_version",
            "dbt catalog schema v1 is required",
        )
    nodes = _mapping(root.get("nodes"), "catalog.nodes")
    catalog_errors = root.get("errors", MISSING)
    if catalog_errors not in (MISSING, None, []):
        if isinstance(catalog_errors, list):
            raise manifest_validator.ArtifactShapeError(
                "CATALOG_ERRORS_PRESENT",
                "catalog.errors",
                "catalog errors must be absent or empty",
            )
        raise manifest_validator.ArtifactShapeError(
            "INVALID_ARTIFACT_SHAPE",
            "catalog.errors",
            "catalog errors must be null or a list",
        )
    for uid in sorted(nodes):
        node = nodes[uid]
        if not isinstance(uid, str) or not isinstance(node, dict):
            raise manifest_validator.ArtifactShapeError(
                "INVALID_ARTIFACT_SHAPE",
                "catalog.nodes",
                "catalog node keys and values must be string/mapping pairs",
            )
        columns = _mapping(node.get("columns"), f"catalog.nodes.{uid}.columns")
        for column_name in sorted(columns):
            column = columns[column_name]
            column_path = f"catalog.nodes.{uid}.columns.{column_name}"
            if not isinstance(column_name, str) or not isinstance(column, dict):
                raise manifest_validator.ArtifactShapeError(
                    "INVALID_ARTIFACT_SHAPE",
                    f"catalog.nodes.{uid}.columns",
                    "catalog column keys and values must be string/mapping pairs",
                )
            if "name" in column and column.get("name") != column_name:
                raise manifest_validator.ArtifactShapeError(
                    "CATALOG_COLUMN_NAME_MISMATCH",
                    f"{column_path}.name",
                    "catalog column.name must match its mapping key",
                )
            _nonempty_string(
                column.get("type"),
                "INVALID_CATALOG_COLUMN_TYPE",
                f"{column_path}.type",
                "catalog column type must be a nonempty string",
            )
            index = column.get("index", MISSING)
            if isinstance(index, bool) or not isinstance(index, int):
                raise manifest_validator.ArtifactShapeError(
                    "INVALID_CATALOG_COLUMN_INDEX",
                    f"{column_path}.index",
                    "catalog column index must be an integer",
                )
    return metadata, nodes


def _normalize_type(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.strip().casefold())
    normalized = re.sub(r"\s*\(\s*", "(", normalized)
    normalized = re.sub(r"\s*,\s*", ",", normalized)
    normalized = re.sub(r"\s*\)", ")", normalized)
    return {"int": "integer", "double precision": "double"}.get(
        normalized, normalized
    )


def _comparison_errors(
    declared_resources: Sequence[Mapping[str, object]],
    catalog_nodes: Mapping[str, object],
) -> list[dict[str, object]]:
    errors: list[dict[str, object]] = []
    for resource in sorted(declared_resources, key=lambda item: str(item["unique_id"])):
        uid = str(resource["unique_id"])
        physical_node = catalog_nodes.get(uid)
        if physical_node is None:
            errors.append(
                _error(
                    "MISSING_PHYSICAL_RELATION",
                    f"catalog.nodes.{uid}",
                    "declared public relation is missing from catalog.nodes",
                    uid=uid,
                    column=None,
                )
            )
            continue
        physical_columns = physical_node["columns"]
        declared_columns = {
            str(column["name"]): column for column in resource["columns"]
        }
        declared_order = list(resource["public_gold"]["column_order"])
        declared_names = set(declared_columns)
        physical_names = set(physical_columns)
        for column_name in sorted(declared_names - physical_names):
            errors.append(
                _error(
                    "MISSING_PHYSICAL_COLUMN",
                    f"catalog.nodes.{uid}.columns.{column_name}",
                    "declared column is missing from the physical catalog relation",
                    uid=uid,
                    column=column_name,
                    declared_type=declared_columns[column_name]["data_type"],
                    physical_type=None,
                )
            )
        for column_name in sorted(physical_names - declared_names):
            physical_column = physical_columns[column_name]
            errors.append(
                _error(
                    "EXTRA_PHYSICAL_COLUMN",
                    f"catalog.nodes.{uid}.columns.{column_name}",
                    "physical catalog column is not present in the declaration",
                    uid=uid,
                    column=column_name,
                    declared_type=None,
                    physical_type=physical_column["type"],
                    physical_index=physical_column["index"],
                )
            )
        for column_name in sorted(declared_names & physical_names):
            declared_type = str(declared_columns[column_name]["data_type"])
            physical_type = str(physical_columns[column_name]["type"])
            if _normalize_type(declared_type) != _normalize_type(physical_type):
                errors.append(
                    _error(
                        "INCOMPATIBLE_COLUMN_TYPE",
                        f"catalog.nodes.{uid}.columns.{column_name}.type",
                        "declared and physical catalog column types are incompatible",
                        uid=uid,
                        column=column_name,
                        declared_type=declared_type,
                        physical_type=physical_type,
                        physical_index=physical_columns[column_name]["index"],
                    )
                )

        index_to_columns: dict[int, list[str]] = {}
        for column_name in sorted(physical_columns):
            index = physical_columns[column_name]["index"]
            index_to_columns.setdefault(index, []).append(column_name)
        for index in sorted(index_to_columns):
            duplicate_columns = index_to_columns[index]
            if len(duplicate_columns) < 2:
                continue
            for column_name in duplicate_columns:
                errors.append(
                    _error(
                        "DUPLICATE_PHYSICAL_INDEX",
                        f"catalog.nodes.{uid}.columns.{column_name}.index",
                        "physical catalog column index is duplicated",
                        uid=uid,
                        column=column_name,
                        physical_index=index,
                    )
                )
        ordered_physical = sorted(
            physical_columns,
            key=lambda name: (physical_columns[name]["index"], name),
        )
        expected_indexes = list(range(1, len(physical_columns) + 1))
        actual_indexes = [physical_columns[name]["index"] for name in ordered_physical]
        if actual_indexes != expected_indexes:
            for expected_index, column_name in enumerate(ordered_physical, start=1):
                physical_index = physical_columns[column_name]["index"]
                if physical_index == expected_index:
                    continue
                errors.append(
                    _error(
                        "NONCONTIGUOUS_PHYSICAL_INDEX",
                        f"catalog.nodes.{uid}.columns.{column_name}.index",
                        "physical catalog indexes must be exactly contiguous from 1 through N",
                        uid=uid,
                        column=column_name,
                        expected_index=expected_index,
                        physical_index=physical_index,
                    )
                )
        elif declared_names == physical_names and ordered_physical != declared_order:
            physical_positions = {
                column_name: physical_columns[column_name]["index"]
                for column_name in ordered_physical
            }
            for declared_index, column_name in enumerate(declared_order, start=1):
                physical_index = physical_positions[column_name]
                if declared_index == physical_index:
                    continue
                errors.append(
                    _error(
                        "PHYSICAL_COLUMN_ORDER_MISMATCH",
                        f"catalog.nodes.{uid}.columns.{column_name}.index",
                        "physical catalog order differs from public_gold.column_order",
                        uid=uid,
                        column=column_name,
                        declared_index=declared_index,
                        physical_index=physical_index,
                    )
                )
    return errors


def compare_public_gold_catalog(
    manifest: object,
    catalog: object,
    resources: Iterable[str] | None = None,
    required_language: str = "ko-KR",
    evidence_kind: str = "fixture",
    evidence_id: str | None = None,
) -> dict[str, object]:
    normalized_evidence_id, evidence_error = _validate_evidence_argument(
        evidence_kind, evidence_id
    )
    if evidence_error is not None:
        return _report(
            "ERROR",
            [evidence_error],
            declared_status="NOT_RUN",
            comparison_status="NOT_RUN",
            evidence_kind=evidence_kind,
            evidence_id=None,
            required_language=required_language,
        )

    selected = list(resources) if resources is not None else None
    declared_report, declared_catalog = manifest_validator.validate_manifest(
        manifest, resources=selected, required_language=required_language
    )
    if declared_report["status"] != "PASS":
        validator_status = str(declared_report["status"])
        declared_status = "FAIL" if validator_status == "FAIL" else "NOT_RUN"
        return _report(
            validator_status,
            declared_report.get("errors", []),
            declared_status=declared_status,
            comparison_status="NOT_RUN",
            evidence_kind=evidence_kind,
            evidence_id=normalized_evidence_id,
            required_language=required_language,
            resources=declared_report.get("resources", []),
        )

    if declared_catalog is None:
        return _report(
            "ERROR",
            [_error("DECLARED_CATALOG_MISSING", "manifest", "validator did not produce declarations")],
            declared_status="PASS",
            comparison_status="NOT_RUN",
            evidence_kind=evidence_kind,
            evidence_id=normalized_evidence_id,
            required_language=required_language,
        )
    declared_resources = list(declared_catalog["resources"])
    declared_uids = [str(resource["unique_id"]) for resource in declared_resources]
    if selected is not None:
        nonpublishable = sorted(
            set(declared_report.get("resources", [])) - set(declared_uids)
        )
        if nonpublishable:
            return _report(
                "FAIL",
                [
                    _error(
                        "RESOURCE_NOT_PUBLISHABLE",
                        f"nodes.{uid}.config.meta.public_gold.visibility",
                        "selected resource is not published_producer or served",
                        uid=uid,
                        column=None,
                    )
                    for uid in nonpublishable
                ],
                declared_status="PASS",
                comparison_status="NOT_RUN",
                evidence_kind=evidence_kind,
                evidence_id=normalized_evidence_id,
                required_language=required_language,
                resources=nonpublishable,
            )
    if not declared_resources:
        return _report(
            "FAIL",
            [
                _error(
                    "NO_PUBLISHABLE_RESOURCES",
                    "resources",
                    "no published_producer or served resources were selected",
                )
            ],
            declared_status="PASS",
            comparison_status="NOT_RUN",
            evidence_kind=evidence_kind,
            evidence_id=normalized_evidence_id,
            required_language=required_language,
        )

    try:
        catalog_metadata, catalog_nodes = _validated_catalog(catalog)
        manifest_root = _mapping(manifest, "manifest")
        manifest_metadata = _mapping(manifest_root.get("metadata"), "manifest.metadata")
        manifest_invocation_id = _nonempty_string(
            manifest_metadata.get("invocation_id"),
            "MISSING_INVOCATION_ID",
            "manifest.metadata.invocation_id",
            "manifest invocation_id must be a nonempty string",
        )
        catalog_invocation_id = _nonempty_string(
            catalog_metadata.get("invocation_id"),
            "MISSING_INVOCATION_ID",
            "catalog.metadata.invocation_id",
            "catalog invocation_id must be a nonempty string",
        )
        if manifest_invocation_id != catalog_invocation_id:
            raise manifest_validator.ArtifactShapeError(
                "INVOCATION_ID_MISMATCH",
                "catalog.metadata.invocation_id",
                "manifest and catalog invocation_id values must match exactly",
            )
    except manifest_validator.ArtifactShapeError as error:
        return _report(
            "ERROR",
            [_error(error.code, error.path, error.message)],
            declared_status="PASS",
            comparison_status="NOT_RUN",
            evidence_kind=evidence_kind,
            evidence_id=normalized_evidence_id,
            required_language=required_language,
            resources=declared_uids,
        )

    differences = _comparison_errors(declared_resources, catalog_nodes)
    comparison_status = "FAIL" if differences else "PASS"
    return _report(
        comparison_status,
        differences,
        declared_status="PASS",
        comparison_status=comparison_status,
        evidence_kind=evidence_kind,
        evidence_id=normalized_evidence_id,
        required_language=required_language,
        resources=declared_uids,
    )


def _argument_parser() -> argparse.ArgumentParser:
    parser = ReportArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="dbt manifest v12 JSON path")
    parser.add_argument("--catalog", required=True, help="dbt catalog v1 JSON path")
    parser.add_argument("--resource", action="append", help="model name or unique ID")
    parser.add_argument("--require-language", required=True, help="required documentation language")
    parser.add_argument(
        "--evidence-kind",
        choices=sorted(EVIDENCE_KINDS),
        default="fixture",
        help="fixture or operator-asserted approved dev catalog",
    )
    parser.add_argument("--evidence-id", help="non-secret operator evidence identifier")
    parser.add_argument("--output", help="write comparison report JSON")
    return parser


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON constant is unsupported: {value}")


def _load_json(path: Path, label: str) -> object:
    if path.is_symlink() or not path.is_file():
        raise OSError(f"{label} must be an existing regular non-symlink file")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle, parse_constant=_reject_json_constant)


def _validated_output_path(output: Path, inputs: Sequence[Path]) -> Path:
    requested = output.expanduser().absolute()
    if requested.is_symlink():
        raise OSError("output symlinks are unsupported")
    if not requested.parent.is_dir():
        raise OSError("output parent must be an existing directory")
    if requested.exists() and not requested.is_file():
        raise OSError("output must be a regular file")
    resolved_inputs = [path.resolve(strict=True) for path in inputs]
    for input_path in inputs:
        if requested.exists() and os.path.samefile(requested, input_path):
            raise OSError("output must not overwrite an input artifact")
    canonical = (
        requested.resolve(strict=True)
        if requested.exists()
        else requested.parent.resolve(strict=True) / requested.name
    )
    if canonical in resolved_inputs:
        raise OSError("output must not overwrite an input artifact")
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
            declared_status="NOT_RUN",
            comparison_status="NOT_RUN",
            evidence_kind="fixture",
            evidence_id=None,
            required_language="",
        )
        write_utf8_stdout(render_json(report))
        return 2

    evidence_id, evidence_error = _validate_evidence_argument(
        arguments.evidence_kind, arguments.evidence_id
    )
    if evidence_error is not None:
        report = _report(
            "ERROR",
            [evidence_error],
            declared_status="NOT_RUN",
            comparison_status="NOT_RUN",
            evidence_kind=arguments.evidence_kind,
            evidence_id=None,
            required_language=arguments.require_language,
        )
        write_utf8_stdout(render_json(report))
        return 2
    manifest_path = Path(arguments.manifest).expanduser().absolute()
    catalog_path = Path(arguments.catalog).expanduser().absolute()
    try:
        manifest = _load_json(manifest_path, "manifest")
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        report = _report(
            "ERROR",
            [_error("MANIFEST_READ_ERROR", "manifest", f"cannot read manifest JSON: {error}")],
            declared_status="NOT_RUN",
            comparison_status="NOT_RUN",
            evidence_kind=arguments.evidence_kind,
            evidence_id=evidence_id,
            required_language=arguments.require_language,
        )
        write_utf8_stdout(render_json(report))
        return 2
    try:
        catalog = _load_json(catalog_path, "catalog")
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        report = _report(
            "ERROR",
            [_error("CATALOG_READ_ERROR", "catalog", f"cannot read catalog JSON: {error}")],
            declared_status="NOT_RUN",
            comparison_status="NOT_RUN",
            evidence_kind=arguments.evidence_kind,
            evidence_id=evidence_id,
            required_language=arguments.require_language,
        )
        write_utf8_stdout(render_json(report))
        return 2

    report = compare_public_gold_catalog(
        manifest,
        catalog,
        resources=arguments.resource,
        required_language=arguments.require_language,
        evidence_kind=arguments.evidence_kind,
        evidence_id=evidence_id,
    )
    if report["status"] != "ERROR" and arguments.output:
        try:
            output = _validated_output_path(
                Path(arguments.output), (manifest_path, catalog_path)
            )
            _atomic_write(output, render_json(report))
        except (OSError, UnicodeError) as error:
            report = _with_output_error(
                report,
                _error(
                    "OUTPUT_WRITE_ERROR",
                    "output",
                    f"cannot write report: {error}",
                ),
            )
    write_utf8_stdout(render_json(report))
    return {"PASS": 0, "FAIL": 1, "ERROR": 2}[str(report["status"])]


if __name__ == "__main__":
    raise SystemExit(main())
