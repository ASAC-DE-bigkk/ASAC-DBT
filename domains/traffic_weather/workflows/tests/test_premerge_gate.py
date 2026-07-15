from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
MODULE_PATH = PROJECT_ROOT / "workflows" / "premerge_gate.py"


def _load_module():
    assert MODULE_PATH.is_file(), "domain-owned pre-merge workflow Module is missing"
    spec = importlib.util.spec_from_file_location("traffic_weather_premerge_gate", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RecordingRunner:
    def __init__(
        self,
        changed_files: str,
        *,
        empty_selector: str | None = None,
    ) -> None:
        self.changed_files = changed_files
        self.empty_selector = empty_selector
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, command, **kwargs):
        command = [str(part) for part in command]
        self.calls.append((command, kwargs))
        stdout = ""
        if command[:3] == ["git", "diff", "--name-only"]:
            stdout = self.changed_files
        elif command[:2] == ["dbt", "ls"]:
            selector = command[command.index("--selector") + 1]
            stdout = "" if selector == self.empty_selector else f"selected__{selector}\n"
        return subprocess.CompletedProcess(command, 0, stdout=stdout)


def _project(tmp_path: Path, selectors: tuple[str, ...] = ("alpha", "beta")) -> Path:
    project_dir = tmp_path / "domains" / "traffic_weather"
    project_dir.mkdir(parents=True)
    (project_dir / "selectors.yml").write_text(
        yaml.safe_dump(
            {
                "selectors": [
                    {"name": name, "definition": {"method": "tag", "value": name}}
                    for name in selectors
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return project_dir


@pytest.mark.parametrize(
    "path",
    (
        "domains/traffic_weather/models/traffic/new.sql",
        "packages/asac_axes/models/dim_admin_dong.sql",
        ".github/workflows/traffic-weather-monoproject-premerge-gate.yml",
        ".gitignore",
    ),
)
def test_scope_includes_every_owned_change(path: str) -> None:
    module = _load_module()

    assert module.is_monoproject_relevant((path,))


def test_scope_excludes_unowned_domains() -> None:
    module = _load_module()

    assert not module.is_monoproject_relevant(
        ("domains/culture/models/events.sql", "docs/team.md")
    )


def test_scope_cli_needs_no_installed_project_dependencies(tmp_path: Path) -> None:
    github_output = tmp_path / "github-output.txt"

    subprocess.run(
        [
            sys.executable,
            "-S",
            str(MODULE_PATH),
            "scope",
            "--repository-root",
            str(REPOSITORY_ROOT),
            "--base-sha",
            "HEAD",
            "--head-sha",
            "HEAD",
            "--github-output",
            str(github_output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert github_output.read_text(encoding="utf-8") == "monoproject_relevant=false\n"


def test_unowned_change_is_a_successful_no_op(tmp_path: Path, capsys) -> None:
    module = _load_module()
    project_dir = _project(tmp_path)
    runner = RecordingRunner("domains/culture/models/events.sql\n")

    executed = module.run_premerge_gate(
        repository_root=tmp_path,
        project_dir=project_dir,
        target_path=tmp_path / "target",
        base_sha="base",
        head_sha="head",
        command_runner=runner,
    )

    assert executed is False
    assert [call[0] for call in runner.calls] == [
        ["git", "diff", "--name-only", "base", "head", "--"]
    ]
    assert "not required" in capsys.readouterr().out


def test_gate_owns_the_complete_read_only_premerge_sequence(tmp_path: Path) -> None:
    module = _load_module()
    project_dir = _project(tmp_path)
    target_path = tmp_path / "target" / "manifest-gate"
    runner = RecordingRunner("domains/traffic_weather/models/weather/new.sql\n")

    executed = module.run_premerge_gate(
        repository_root=tmp_path,
        project_dir=project_dir,
        target_path=target_path,
        base_sha="base",
        head_sha="head",
        dbt_bin="dbt",
        snapshot_run_id="ci__snapshot",
        command_runner=runner,
    )

    assert executed is True
    commands = [call[0] for call in runner.calls]
    assert commands[0] == ["git", "diff", "--name-only", "base", "head", "--"]
    assert commands[1] == ["dbt", "deps"]
    assert commands[2][:5] == [
        "dbt",
        "parse",
        "--no-partial-parse",
        "--target",
        "dev",
    ]
    assert commands[3][:4] == ["dbt", "ls", "--selector", "alpha"]
    assert commands[4][:4] == ["dbt", "ls", "--selector", "beta"]
    assert commands[5] == [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    assert commands[6] == [
        sys.executable,
        str(
            project_dir
            / "contracts"
            / "traffic"
            / "scripts"
            / "validate_singular_test_dependency_manifest.py"
        ),
        "--manifest",
        str(target_path / "manifest.json"),
    ]

    parse_command = commands[2]
    assert parse_command[parse_command.index("--target-path") + 1] == str(target_path)
    assert "ci__snapshot" in parse_command[parse_command.index("--vars") + 1]

    for _, kwargs in runner.calls[1:5]:
        assert kwargs["cwd"] == project_dir
        assert kwargs["check"] is True
        assert kwargs["env"]["DBT_PROJECT_DIR"] == str(project_dir)
        assert kwargs["env"]["DBT_PROFILES_DIR"] == str(project_dir)
        assert kwargs["env"]["DBT_TARGET"] == "dev"

    pytest_environment = runner.calls[5][1]["env"]
    assert pytest_environment["ASK_SEOUL_FRESH_MANIFEST"] == str(
        target_path / "manifest.json"
    )


def test_empty_named_selector_fails_before_contract_tests(tmp_path: Path) -> None:
    module = _load_module()
    project_dir = _project(tmp_path, selectors=("empty",))
    runner = RecordingRunner(
        "domains/traffic_weather/selectors.yml\n", empty_selector="empty"
    )

    with pytest.raises(RuntimeError, match="empty.*empty"):
        module.run_premerge_gate(
            repository_root=tmp_path,
            project_dir=project_dir,
            target_path=tmp_path / "target",
            base_sha="base",
            head_sha="head",
            command_runner=runner,
        )

    assert all("pytest" not in command for command, _ in runner.calls)
    assert all(
        "validate_singular_test_dependency_manifest.py" not in " ".join(command)
        for command, _ in runner.calls
    )
