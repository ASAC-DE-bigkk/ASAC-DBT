"""Internal _catalog_contract cli responsibility."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from contracts.engine.artifact_io import atomic_write_utf8_text, write_utf8_stdout

from .comparison import compare_public_gold_catalog

from .reporting import (
    EVIDENCE_KINDS,
    _error,
    _report,
    _validate_evidence_argument,
    _with_output_error,
    render_json,
)


class CliArgumentError(Exception):
    pass


class ReportArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliArgumentError(message)


def _argument_parser() -> argparse.ArgumentParser:
    parser = ReportArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="dbt manifest v12 JSON path")
    parser.add_argument("--catalog", required=True, help="dbt catalog v1 JSON path")
    parser.add_argument("--resource", action="append", help="model name or unique ID")
    parser.add_argument(
        "--require-language", required=True, help="required documentation language"
    )
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
            [
                _error(
                    "MANIFEST_READ_ERROR",
                    "manifest",
                    f"cannot read manifest JSON: {error}",
                )
            ],
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
            [
                _error(
                    "CATALOG_READ_ERROR",
                    "catalog",
                    f"cannot read catalog JSON: {error}",
                )
            ],
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
            atomic_write_utf8_text(output, render_json(report))
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
