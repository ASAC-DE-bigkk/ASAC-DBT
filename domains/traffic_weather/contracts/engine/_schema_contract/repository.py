"""Internal _schema_contract repository responsibility."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .types import YAML_SUFFIXES


def _nearest_project_scope(path: Path, fallback_scope: Path) -> str:
    for ancestor in (path.parent, *path.parents[1:]):
        marker = ancestor / "dbt_project.yml"
        if marker.is_file() and not marker.is_symlink():
            return ancestor.resolve().as_posix()
    return fallback_scope.as_posix()


def _cross_file_duplicate_errors(
    resources: Iterable[dict[str, object]],
) -> list[dict[str, object]]:
    first_by_identity: dict[tuple[str, str, str], dict[str, object]] = {}
    errors: list[dict[str, object]] = []
    ordered = sorted(
        resources,
        key=lambda item: (
            str(item["project_scope"]),
            str(item["kind"]),
            str(item["name"]),
            str(item["file"]),
            int(item["line"]),
        ),
    )
    for resource in ordered:
        identity = (
            str(resource["project_scope"]),
            str(resource["kind"]),
            str(resource["name"]),
        )
        first = first_by_identity.get(identity)
        if first is None:
            first_by_identity[identity] = resource
            continue
        if first["file"] == resource["file"]:
            continue
        files = [str(first["file"]), str(resource["file"])]
        lines = [int(first["line"]), int(resource["line"])]
        errors.append(
            {
                "code": "DUPLICATE_RESOURCE",
                "file": files[0],
                "files": files,
                "lines": lines,
                "message": (
                    f"duplicate {resource['kind']} resource '{resource['name']}' "
                    "across schema files in one dbt project"
                ),
                "project_scope": str(resource["project_scope"]),
                "resource_kind": str(resource["kind"]),
                "resource_name": str(resource["name"]),
            }
        )
    return errors


def _discover_files(
    schema_roots: Iterable[str | Path],
) -> tuple[list[Path], list[dict[str, object]]]:
    paths: set[Path] = set()
    errors: list[dict[str, object]] = []
    roots = sorted(
        {Path(root).expanduser().absolute() for root in schema_roots},
        key=lambda path: path.as_posix(),
    )
    if not roots:
        return [], [
            {"code": "INVALID_ROOT", "message": "at least one schema root is required"}
        ]
    for requested_root in roots:
        if requested_root.is_symlink():
            errors.append(
                {
                    "code": "PATH_UNSAFE",
                    "message": f"schema root symlinks are unsupported: {requested_root.as_posix()}",
                    "path": requested_root.as_posix(),
                }
            )
            continue
        if not requested_root.exists():
            errors.append(
                {
                    "code": "INVALID_ROOT",
                    "message": f"schema root does not exist: {requested_root.as_posix()}",
                    "path": requested_root.as_posix(),
                }
            )
            continue
        try:
            root = requested_root.resolve(strict=True)
        except OSError as error:
            errors.append(
                {
                    "code": "IO_ERROR",
                    "message": f"cannot resolve schema root {requested_root.as_posix()}: {error}",
                    "path": requested_root.as_posix(),
                }
            )
            continue

        if root.is_file():
            if root.suffix.lower() not in YAML_SUFFIXES:
                errors.append(
                    {
                        "code": "INVALID_ROOT",
                        "message": f"schema root file is not YAML: {root.as_posix()}",
                        "path": root.as_posix(),
                    }
                )
            else:
                paths.add(root)
        elif root.is_dir():
            try:
                candidates = sorted(root.rglob("*"), key=lambda path: path.as_posix())
                for candidate in candidates:
                    if candidate.is_symlink():
                        errors.append(
                            {
                                "code": "PATH_UNSAFE",
                                "message": f"symlinks under schema roots are unsupported: {candidate.as_posix()}",
                                "path": candidate.as_posix(),
                            }
                        )
                        continue
                    if (
                        not candidate.is_file()
                        or candidate.suffix.lower() not in YAML_SUFFIXES
                    ):
                        continue
                    resolved_candidate = candidate.resolve(strict=True)
                    try:
                        resolved_candidate.relative_to(root)
                    except ValueError:
                        errors.append(
                            {
                                "code": "PATH_UNSAFE",
                                "message": f"discovered YAML escapes schema root: {candidate.as_posix()}",
                                "path": candidate.as_posix(),
                            }
                        )
                        continue
                    paths.add(resolved_candidate)
            except OSError as error:
                errors.append(
                    {
                        "code": "IO_ERROR",
                        "message": f"cannot discover YAML under {root.as_posix()}: {error}",
                        "path": root.as_posix(),
                    }
                )
        else:
            errors.append(
                {
                    "code": "INVALID_ROOT",
                    "message": f"schema root is neither a file nor directory: {root.as_posix()}",
                    "path": root.as_posix(),
                }
            )
    if not errors and not paths:
        errors.append(
            {
                "code": "INVALID_ROOT",
                "message": "schema roots contain no .yml or .yaml files",
            }
        )
    return sorted(paths, key=lambda path: path.as_posix()), errors
