"""Traffic source freshness SLO environment contract."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
WARN_ENV = "ASK_SEOUL_REPORT_TRAFFIC_FRESHNESS_WARN_MINUTES"
ERROR_ENV = "ASK_SEOUL_REPORT_TRAFFIC_FRESHNESS_ERROR_MINUTES"
MANIFEST_SOURCE_ID = "source.asac_seoul.traffic_bronze.collection_run_manifest"
INCIDENT_SOURCE_ID = "source.asac_seoul.traffic_bronze.seoul_traffic_incident"
AUDIT_SOURCE_ID = (
    "source.asac_seoul.traffic_bronze.seoul_traffic_incident_request_audit"
)


def _dbt_executable() -> str:
    configured = os.environ.get("DBT_BIN")
    if configured:
        return configured

    executable = shutil.which("dbt")
    if executable:
        return executable

    runtime_dbt = Path("/home/airflow/dbt-venv/bin/dbt")
    if runtime_dbt.is_file():
        return str(runtime_dbt)

    pytest.skip("dbt 실행 파일이 없어 resolved manifest 계약은 런타임 검증으로 이관")


def _parse_manifest(
    tmp_path: Path,
    *,
    warn_minutes: int | None,
    error_minutes: int | None,
) -> dict:
    dbt_executable = _dbt_executable()
    case_name = f"{warn_minutes or 'default'}-{error_minutes or 'default'}"
    project_root = tmp_path / f"dbt-root-{case_name}"
    target_path = tmp_path / f"target-{case_name}"
    log_path = tmp_path / f"logs-{case_name}"
    environment = os.environ.copy()

    project_root.mkdir()
    for filename in (
        "dbt_project.yml",
        "profiles.yml",
        "selectors.yml",
    ):
        shutil.copy2(PROJECT_ROOT / filename, project_root / filename)
    for directory in ("models", "tests", "macros", "seeds"):
        shutil.copytree(PROJECT_ROOT / directory, project_root / directory)

    package_root = project_root / "packages" / "asac_axes"
    shutil.copytree(REPOSITORY_ROOT / "packages" / "asac_axes", package_root)
    (project_root / "packages.yml").write_text(
        "packages:\n  - local: packages/asac_axes\n",
        encoding="utf-8",
    )

    environment["DBT_PACKAGES_INSTALL_PATH"] = str(
        tmp_path / f"dbt-packages-{case_name}"
    )
    environment["DBT_SEND_ANONYMOUS_USAGE_STATS"] = "false"

    for key, value in (
        (WARN_ENV, warn_minutes),
        (ERROR_ENV, error_minutes),
    ):
        if value is None:
            environment.pop(key, None)
        else:
            environment[key] = str(value)

    deps_result = subprocess.run(
        [
            dbt_executable,
            "deps",
            "--project-dir",
            str(project_root),
            "--profiles-dir",
            str(project_root),
            "--no-use-colors",
        ],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )
    assert deps_result.returncode == 0, deps_result.stdout + deps_result.stderr

    result = subprocess.run(
        [
            dbt_executable,
            "parse",
            "--project-dir",
            str(project_root),
            "--profiles-dir",
            str(project_root),
            "--target",
            "dev",
            "--vars",
            json.dumps({"traffic_snapshot_dag_run_id": "contract-test-run"}),
            "--no-partial-parse",
            "--target-path",
            str(target_path),
            "--log-path",
            str(log_path),
            "--no-use-colors",
        ],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads((target_path / "manifest.json").read_text(encoding="utf-8"))


def _freshness(manifest: dict, source_id: str) -> dict | None:
    return manifest["sources"][source_id]["freshness"]


@pytest.mark.parametrize(
    ("warn_minutes", "error_minutes", "expected_warn", "expected_error"),
    [
        (None, None, 15, 30),
        (21, 42, 21, 42),
    ],
)
def test_traffic_freshness_resolves_defaults_and_overrides_in_dbt_manifest(
    tmp_path: Path,
    warn_minutes: int | None,
    error_minutes: int | None,
    expected_warn: int,
    expected_error: int,
):
    manifest = _parse_manifest(
        tmp_path,
        warn_minutes=warn_minutes,
        error_minutes=error_minutes,
    )

    manifest_freshness = _freshness(manifest, MANIFEST_SOURCE_ID)
    assert manifest_freshness["warn_after"] == {
        "count": expected_warn,
        "period": "minute",
    }
    assert manifest_freshness["error_after"] == {
        "count": expected_error,
        "period": "minute",
    }
    assert expected_warn < expected_error
    assert _freshness(manifest, INCIDENT_SOURCE_ID) is None
    assert _freshness(manifest, AUDIT_SOURCE_ID) is None
