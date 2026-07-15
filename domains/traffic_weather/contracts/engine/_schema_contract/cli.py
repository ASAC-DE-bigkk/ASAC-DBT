"""Internal _schema_contract cli responsibility."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, Sequence

from contracts.engine.artifact_io import atomic_write_utf8_text, write_utf8_stdout

from .reporting import render_report

from .service import lint_schema_contracts

from .types import YAML_SUFFIXES


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--schema-root", action="append", required=True, help="YAML file or directory"
    )
    parser.add_argument("--resource", action="append", help="governed resource name")
    parser.add_argument(
        "--require-language", required=True, help="required description language"
    )
    parser.add_argument(
        "--output", help="write JSON report to this existing-parent path"
    )
    return parser


def _validate_output_path(
    output: Path,
    report: dict[str, object],
    schema_roots: Iterable[str | Path],
) -> tuple[Path | None, str | None]:
    requested = output.expanduser().absolute()
    if requested.is_symlink():
        return None, f"output symlinks are unsupported: {requested.as_posix()}"
    parent = requested.parent
    if not parent.exists() or not parent.is_dir():
        return None, f"output parent is not an existing directory: {parent.as_posix()}"
    if requested.exists() and not requested.is_file():
        return None, f"output path is not a regular file: {requested.as_posix()}"

    try:
        canonical_output = parent.resolve(strict=True) / requested.name
    except OSError as error:
        return None, f"cannot resolve output parent {parent.as_posix()}: {error}"
    input_paths = {
        Path(str(item["path"])).resolve(strict=False)
        for item in report.get("files", [])
        if isinstance(item, dict) and "path" in item
    }
    protected_directories: set[Path] = set()
    for root_value in schema_roots:
        raw_root = Path(root_value).expanduser().absolute()
        canonical_root = raw_root.resolve(strict=False)
        input_paths.add(canonical_root)
        if canonical_root.is_dir():
            protected_directories.add(canonical_root)
            try:
                requested.relative_to(raw_root)
            except ValueError:
                pass
            else:
                return (
                    None,
                    f"output path is inside a schema root: {requested.as_posix()}",
                )
            try:
                for candidate in canonical_root.rglob("*"):
                    resolved_candidate = candidate.resolve(strict=False)
                    if candidate.is_symlink():
                        if resolved_candidate.is_dir():
                            protected_directories.add(resolved_candidate)
                        else:
                            input_paths.add(resolved_candidate)
                    if (
                        candidate.is_file()
                        and candidate.suffix.lower() in YAML_SUFFIXES
                    ):
                        input_paths.add(resolved_candidate)
            except OSError:
                pass
    for protected_directory in sorted(
        protected_directories, key=lambda path: path.as_posix()
    ):
        try:
            canonical_output.relative_to(protected_directory)
        except ValueError:
            continue
        return None, f"output path is inside a schema root: {requested.as_posix()}"
    if canonical_output in input_paths:
        return (
            None,
            f"output path collides with a discovered YAML input: {requested.as_posix()}",
        )
    return canonical_output, None


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _argument_parser().parse_args(argv)
    report = lint_schema_contracts(
        arguments.schema_root,
        resources=arguments.resource,
        required_language=arguments.require_language,
    )
    rendered = render_report(report)
    if arguments.output:
        output, validation_error = _validate_output_path(
            Path(arguments.output), report, arguments.schema_root
        )
        if validation_error is not None or output is None:
            print(
                f"cannot write output '{arguments.output}': {validation_error}",
                file=sys.stderr,
            )
            return 2
        try:
            atomic_write_utf8_text(output, rendered)
        except (OSError, UnicodeError) as error:
            print(f"cannot write output '{output}': {error}", file=sys.stderr)
            return 2
    else:
        write_utf8_stdout(rendered)
    return {"PASS": 0, "FAIL": 1, "ERROR": 2}[str(report["status"])]
