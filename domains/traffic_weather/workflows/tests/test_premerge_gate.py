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
EXPECTED_GOLD_SELECTOR_COUNTS = {
    "ask_seoul_traffic_transform_gold_gate_tests": 125,
    "ask_seoul_traffic_transform_gold_hourly_tests": 145,
    "ask_seoul_traffic_transform_gold_full_tests": 175,
}


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
        selector_counts: dict[str, int] | None = None,
    ) -> None:
        self.changed_files = changed_files
        self.empty_selector = empty_selector
        self.selector_counts = {
            **EXPECTED_GOLD_SELECTOR_COUNTS,
            **(selector_counts or {}),
        }
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, command, **kwargs):
        command = [str(part) for part in command]
        self.calls.append((command, kwargs))
        stdout = ""
        if command[:3] == ["git", "diff", "--name-only"]:
            stdout = self.changed_files
        elif command[:2] == ["dbt", "ls"]:
            selector = command[command.index("--selector") + 1]
            count = self.selector_counts.get(selector, 1)
            stdout = (
                ""
                if selector == self.empty_selector
                else "".join(
                    f"selected__{selector}__{index}\n" for index in range(count)
                )
            )
        return subprocess.CompletedProcess(command, 0, stdout=stdout)


def _project(
    tmp_path: Path,
    selectors: tuple[str, ...] = tuple(EXPECTED_GOLD_SELECTOR_COUNTS),
) -> Path:
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
    selector_commands = commands[3:6]
    assert [command[3] for command in selector_commands] == list(
        EXPECTED_GOLD_SELECTOR_COUNTS
    )
    assert commands[6] == [
        sys.executable,
        str(
            project_dir
            / "contracts"
            / "traffic"
            / "scripts"
            / "validate_traffic_gold_test_inventory.py"
        ),
        "--manifest",
        str(target_path / "manifest.json"),
        "--inventory",
        str(project_dir / "contracts" / "traffic_gold_test_cadence.yml"),
        "--selector-count",
        "ask_seoul_traffic_transform_gold_gate_tests=125",
        "--selector-count",
        "ask_seoul_traffic_transform_gold_hourly_tests=145",
        "--selector-count",
        "ask_seoul_traffic_transform_gold_full_tests=175",
    ]
    assert commands[7] == [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
    ]
    assert commands[8] == [
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
    vars_payload = parse_command[parse_command.index("--vars") + 1]
    assert "ci__snapshot" in vars_payload
    assert "traffic_snapshot_dag_run_id" in vars_payload
    assert "traffic_flow_snapshot_dag_run_id" in vars_payload

    for _, kwargs in runner.calls[1:6]:
        assert kwargs["cwd"] == project_dir
        assert kwargs["check"] is True
        assert kwargs["env"]["DBT_PROJECT_DIR"] == str(project_dir)
        assert kwargs["env"]["DBT_PROFILES_DIR"] == str(project_dir)
        assert kwargs["env"]["DBT_TARGET"] == "dev"

    pytest_environment = runner.calls[7][1]["env"]
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


@pytest.mark.parametrize(
    "selector,actual_count",
    (
        ("ask_seoul_traffic_transform_gold_gate_tests", 122),
        ("ask_seoul_traffic_transform_gold_hourly_tests", 142),
        ("ask_seoul_traffic_transform_gold_full_tests", 172),
    ),
)
def test_exact_gold_selector_drift_fails_before_contract_tests(
    tmp_path: Path,
    selector: str,
    actual_count: int,
) -> None:
    module = _load_module()
    project_dir = _project(tmp_path)
    runner = RecordingRunner(
        "domains/traffic_weather/selectors.yml\n",
        selector_counts={selector: actual_count},
    )

    with pytest.raises(RuntimeError, match="selector counts mismatch"):
        module.run_premerge_gate(
            repository_root=tmp_path,
            project_dir=project_dir,
            target_path=tmp_path / "target",
            base_sha="base",
            head_sha="head",
            command_runner=runner,
        )

    commands = [command for command, _ in runner.calls]
    assert all("validate_traffic_gold_test_inventory.py" not in " ".join(command) for command in commands)
    assert all("pytest" not in command for command in commands)


def test_traffic_gold_cadence_selectors_are_declared() -> None:
    selectors_path = PROJECT_ROOT / "selectors.yml"
    document = yaml.safe_load(selectors_path.read_text(encoding="utf-8")) or {}
    selector_names = {selector["name"] for selector in document["selectors"]}

    assert "ask_seoul_traffic_transform_gold" in selector_names
    assert "ask_seoul_traffic_transform_gold_models" in selector_names
    assert "ask_seoul_traffic_transform_gold_gate_tests" in selector_names
    assert "ask_seoul_traffic_transform_gold_hourly_tests" in selector_names
    assert "ask_seoul_traffic_transform_gold_full_tests" in selector_names

    def walk(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)

    cadence_definitions = (
        selector["definition"]
        for selector in document["selectors"]
        if selector["name"]
        in {
            "ask_seoul_traffic_transform_gold_gate_tests",
            "ask_seoul_traffic_transform_gold_hourly_tests",
            "ask_seoul_traffic_transform_gold_full_tests",
        }
    )
    assert all(
        node.get("method") != "selector"
        for definition in cadence_definitions
        for node in walk(definition)
    )
