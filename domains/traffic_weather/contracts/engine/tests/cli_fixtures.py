from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENGINE_ROOT = PROJECT_ROOT / "contracts" / "engine"
SCRIPT = ENGINE_ROOT / "lint_schema_contract_source.py"
MANIFEST_SCRIPT = ENGINE_ROOT / "validate_public_gold_manifest.py"
CATALOG_COMPARE_SCRIPT = ENGINE_ROOT / "compare_public_gold_catalog.py"


def write_yaml(root: Path, relative: str, body: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
    return path


def run_cli(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(arg) for arg in args)],
        cwd=PROJECT_ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def run_manifest_cli(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MANIFEST_SCRIPT), *(str(arg) for arg in args)],
        cwd=PROJECT_ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def run_catalog_compare_cli(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CATALOG_COMPARE_SCRIPT), *(str(arg) for arg in args)],
        cwd=PROJECT_ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def run_cli_bytes(
    script: Path,
    *args: object,
    python_io_encoding: str,
    cwd: Path = PROJECT_ROOT,
) -> subprocess.CompletedProcess[bytes]:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = python_io_encoding
    environment.pop("PYTHONPATH", None)
    return subprocess.run(
        [sys.executable, str(script), *(str(arg) for arg in args)],
        cwd=cwd,
        env=environment,
        capture_output=True,
        check=False,
    )
