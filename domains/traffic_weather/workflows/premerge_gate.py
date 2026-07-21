"""Run the read-only Traffic/Weather dbt pre-merge contract workflow."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable, Mapping, Sequence


DEFAULT_SNAPSHOT_RUN_ID = "ci__traffic-weather-monoproject-premerge-gate"
OWNED_PATH_PREFIXES = (
    "domains/traffic_weather/",
    "packages/asac_axes/",
)
OWNED_PATHS = {
    ".github/workflows/traffic-weather-monoproject-premerge-gate.yml",
    ".gitignore",
}
CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
EXACT_SELECTOR_COUNTS = {
    "ask_seoul_traffic_transform_gold_gate_tests": 128,
    "ask_seoul_traffic_transform_gold_hourly_tests": 148,
    "ask_seoul_traffic_transform_gold_full_tests": 178,
}


def _repository_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    return normalized[2:] if normalized.startswith("./") else normalized


def is_monoproject_relevant(changed_paths: Sequence[str]) -> bool:
    """Return whether a repository change belongs to this project boundary."""
    for raw_path in changed_paths:
        path = _repository_path(raw_path.strip())
        if path in OWNED_PATHS or path.startswith(OWNED_PATH_PREFIXES):
            return True
    return False


def _changed_paths(
    repository_root: Path,
    base_sha: str,
    head_sha: str,
    command_runner: CommandRunner,
) -> tuple[str, ...]:
    result = command_runner(
        ["git", "diff", "--name-only", base_sha, head_sha, "--"],
        check=True,
        cwd=repository_root,
        capture_output=True,
        text=True,
    )
    return tuple(path for line in result.stdout.splitlines() if (path := line.strip()))


def evaluate_scope(
    *,
    repository_root: Path,
    base_sha: str,
    head_sha: str,
    command_runner: CommandRunner = subprocess.run,
) -> bool:
    """Evaluate project ownership without importing any project dependency."""
    changed_paths = _changed_paths(
        repository_root.resolve(), base_sha, head_sha, command_runner
    )
    return is_monoproject_relevant(changed_paths)


def write_github_scope_output(output_path: Path, relevant: bool) -> None:
    """Append the scope decision using the GitHub Actions output protocol."""
    with output_path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(f"monoproject_relevant={str(relevant).lower()}\n")


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


def _manifest_vars(snapshot_run_id: str) -> str:
    return json.dumps(
        {
            "traffic_snapshot_dag_run_id": snapshot_run_id,
            "traffic_flow_snapshot_dag_run_id": snapshot_run_id,
            "traffic_citydata_crowding_snapshot_id": 1,
        }
    )


def generate_fresh_manifest(
    *,
    project_dir: Path,
    target_path: Path,
    dbt_bin: str,
    snapshot_run_id: str,
    environment: dict[str, str],
    command_runner: CommandRunner,
) -> Path:
    """Resolve packages and create one non-partial manifest for later gates."""
    command_runner(
        [dbt_bin, "deps"],
        check=True,
        cwd=project_dir,
        env=environment,
    )
    command_runner(
        [
            dbt_bin,
            "parse",
            "--no-partial-parse",
            "--target",
            "dev",
            "--target-path",
            str(target_path),
            "--vars",
            _manifest_vars(snapshot_run_id),
        ],
        check=True,
        cwd=project_dir,
        env=environment,
    )
    return target_path / "manifest.json"


def _selector_names(project_dir: Path) -> tuple[str, ...]:
    import yaml

    document = yaml.safe_load(
        (project_dir / "selectors.yml").read_text(encoding="utf-8")
    )
    selectors = document.get("selectors") if isinstance(document, dict) else None
    if not isinstance(selectors, list) or not selectors:
        raise ValueError("selectors.yml must define at least one named selector")

    names: list[str] = []
    for selector in selectors:
        name = selector.get("name") if isinstance(selector, dict) else None
        if not isinstance(name, str) or not name.strip():
            raise ValueError("every selector must have a non-empty name")
        names.append(name)
    if len(set(names)) != len(names):
        raise ValueError("selector names must be unique")
    return tuple(names)


def validate_named_selectors(
    *,
    project_dir: Path,
    target_path: Path,
    dbt_bin: str,
    snapshot_run_id: str,
    environment: dict[str, str],
    command_runner: CommandRunner,
) -> dict[str, int]:
    """Return selector counts and fail empty or drifted Airflow contracts."""
    counts: dict[str, int] = {}
    for selector in _selector_names(project_dir):
        result = command_runner(
            [
                dbt_bin,
                "ls",
                "--selector",
                selector,
                "--target",
                "dev",
                "--target-path",
                str(target_path),
                "--vars",
                _manifest_vars(snapshot_run_id),
                "--output",
                "name",
                "--quiet",
            ],
            check=True,
            cwd=project_dir,
            env=environment,
            capture_output=True,
            text=True,
        )
        selected = [line for line in result.stdout.splitlines() if line.strip()]
        if not selected:
            raise RuntimeError(f"named selector {selector!r} is empty")
        counts[selector] = len(selected)

    actual_exact = {name: counts.get(name, 0) for name in EXACT_SELECTOR_COUNTS}
    if actual_exact != EXACT_SELECTOR_COUNTS:
        raise RuntimeError(
            "Traffic Gold selector counts mismatch: "
            f"expected {EXACT_SELECTOR_COUNTS}, actual {actual_exact}"
        )
    return counts


def validate_traffic_gold_test_inventory(
    *,
    project_dir: Path,
    manifest_path: Path,
    selector_counts: Mapping[str, int],
    command_runner: CommandRunner,
) -> None:
    """Fail when Traffic Gold cadence inventory differs from the manifest."""
    selector_count_args = [
        item
        for name in EXACT_SELECTOR_COUNTS
        for item in ("--selector-count", f"{name}={selector_counts[name]}")
    ]
    command_runner(
        [
            sys.executable,
            str(
                project_dir
                / "contracts"
                / "traffic"
                / "scripts"
                / "validate_traffic_gold_test_inventory.py"
            ),
            "--manifest",
            str(manifest_path),
            "--inventory",
            str(project_dir / "contracts" / "traffic_gold_test_cadence.yml"),
            *selector_count_args,
        ],
        check=True,
        cwd=project_dir,
    )


def run_premerge_gate(
    *,
    repository_root: Path,
    project_dir: Path,
    target_path: Path,
    base_sha: str,
    head_sha: str,
    dbt_bin: str = "dbt",
    snapshot_run_id: str = DEFAULT_SNAPSHOT_RUN_ID,
    command_runner: CommandRunner = subprocess.run,
) -> bool:
    """Run all project gates, or return ``False`` for an unowned change."""
    repository_root = repository_root.resolve()
    project_dir = project_dir.resolve()
    target_path = target_path.resolve()

    if not evaluate_scope(
        repository_root=repository_root,
        base_sha=base_sha,
        head_sha=head_sha,
        command_runner=command_runner,
    ):
        print("Traffic/Weather monoproject validation is not required for this change.")
        return False

    environment = _dbt_environment(project_dir)
    manifest_path = generate_fresh_manifest(
        project_dir=project_dir,
        target_path=target_path,
        dbt_bin=dbt_bin,
        snapshot_run_id=snapshot_run_id,
        environment=environment,
        command_runner=command_runner,
    )
    selector_counts = validate_named_selectors(
        project_dir=project_dir,
        target_path=target_path,
        dbt_bin=dbt_bin,
        snapshot_run_id=snapshot_run_id,
        environment=environment,
        command_runner=command_runner,
    )
    validate_traffic_gold_test_inventory(
        project_dir=project_dir,
        manifest_path=manifest_path,
        selector_counts=selector_counts,
        command_runner=command_runner,
    )

    test_environment = environment.copy()
    test_environment["ASK_SEOUL_FRESH_MANIFEST"] = str(manifest_path)
    command_runner(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        check=True,
        cwd=project_dir,
        env=test_environment,
    )
    command_runner(
        [
            sys.executable,
            str(
                project_dir
                / "contracts"
                / "traffic"
                / "scripts"
                / "validate_singular_test_dependency_manifest.py"
            ),
            "--manifest",
            str(manifest_path),
        ],
        check=True,
        cwd=project_dir,
    )
    return True


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    scope = commands.add_parser(
        "scope", help="write whether the pull request touches this project"
    )
    scope.add_argument("--repository-root", required=True, type=Path)
    scope.add_argument("--base-sha", required=True)
    scope.add_argument("--head-sha", required=True)
    scope.add_argument("--github-output", required=True, type=Path)

    run = commands.add_parser("run", help="run the complete read-only project gate")
    run.add_argument("--repository-root", required=True, type=Path)
    run.add_argument("--project-dir", required=True, type=Path)
    run.add_argument("--target-path", required=True, type=Path)
    run.add_argument("--base-sha", required=True)
    run.add_argument("--head-sha", required=True)
    run.add_argument("--dbt-bin", default="dbt")
    run.add_argument("--snapshot-run-id", default=DEFAULT_SNAPSHOT_RUN_ID)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _argument_parser().parse_args(argv)
    if args.command == "scope":
        relevant = evaluate_scope(
            repository_root=args.repository_root,
            base_sha=args.base_sha,
            head_sha=args.head_sha,
        )
        write_github_scope_output(args.github_output, relevant)
        return 0

    run_premerge_gate(
        repository_root=args.repository_root,
        project_dir=args.project_dir,
        target_path=args.target_path,
        base_sha=args.base_sha,
        head_sha=args.head_sha,
        dbt_bin=args.dbt_bin,
        snapshot_run_id=args.snapshot_run_id,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
