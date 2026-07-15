"""Internal _manifest_contract cli responsibility."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from contracts.engine.artifact_io import atomic_write_utf8_text, write_utf8_stdout

from .foundation import (
    _error,
    _report,
    render_json,
)

from .service import validate_manifest


class CliArgumentError(Exception):
    pass


class ReportArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliArgumentError(message)


def _argument_parser() -> argparse.ArgumentParser:
    parser = ReportArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="dbt manifest v12 JSON path")
    parser.add_argument("--resource", action="append", help="model name or unique ID")
    parser.add_argument(
        "--require-language", required=True, help="required documentation language"
    )
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
            [
                _error(
                    "MANIFEST_READ_ERROR",
                    "manifest",
                    f"cannot read manifest JSON: {error}",
                )
            ],
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
            atomic_write_utf8_text(output, render_json(catalog))
        except (OSError, UnicodeError) as error:
            report = _report(
                "ERROR",
                [
                    _error(
                        "OUTPUT_WRITE_ERROR", "output", f"cannot write catalog: {error}"
                    )
                ],
                declared_status=str(report["proof"]["declared_contract"]),
                required_language=arguments.require_language,
                resources=report.get("resources", []),
            )
    write_utf8_stdout(render_json(report))
    return {"PASS": 0, "FAIL": 1, "ERROR": 2}[str(report["status"])]
