#!/usr/bin/env python3
"""Run the read-only Traffic singular-test manifest pre-merge gate."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Sequence


DEFAULT_SNAPSHOT_RUN_ID = "ci__traffic-manifest-premerge-gate"
VALIDATOR_SCRIPT = Path(__file__).with_name(
    "validate_singular_test_dependency_manifest.py"
)


def _dbt_environment(project_dir: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "DBT_PROJECT_DIR": str(project_dir),
            "DBT_PROFILES_DIR": str(project_dir),
            "DBT_TARGET": "dev",
        }
    )
    return environment


def run_gate(
    project_dir: Path,
    dbt_bin: str,
    target_path: Path,
    snapshot_run_id: str,
) -> None:
    """Resolve packages, parse a fresh manifest, and validate its test edges."""
    project_dir = project_dir.resolve()
    target_path = target_path.resolve()
    environment = _dbt_environment(project_dir)

    subprocess.run(
        [dbt_bin, "deps"],
        check=True,
        cwd=project_dir,
        env=environment,
    )
    subprocess.run(
        [
            dbt_bin,
            "parse",
            "--no-partial-parse",
            "--target",
            "dev",
            "--target-path",
            str(target_path),
            "--vars",
            json.dumps({"traffic_snapshot_dag_run_id": snapshot_run_id}),
        ],
        check=True,
        cwd=project_dir,
        env=environment,
    )
    subprocess.run(
        [
            sys.executable,
            str(VALIDATOR_SCRIPT),
            "--manifest",
            str(target_path / "manifest.json"),
        ],
        check=True,
        cwd=project_dir,
    )


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", required=True, type=Path)
    parser.add_argument("--dbt-bin", default="dbt")
    parser.add_argument("--target-path", required=True, type=Path)
    parser.add_argument("--snapshot-run-id", default=DEFAULT_SNAPSHOT_RUN_ID)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _argument_parser().parse_args(argv)
    run_gate(
        project_dir=args.project_dir,
        dbt_bin=args.dbt_bin,
        target_path=args.target_path,
        snapshot_run_id=args.snapshot_run_id,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
