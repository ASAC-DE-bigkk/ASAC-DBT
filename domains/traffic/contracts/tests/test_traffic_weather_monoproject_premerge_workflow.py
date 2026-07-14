from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = (
    REPO_ROOT
    / ".github"
    / "workflows"
    / "traffic-weather-monoproject-premerge-gate.yml"
)
LEGACY_WORKFLOW = (
    REPO_ROOT / ".github" / "workflows" / "traffic-manifest-premerge-gate.yml"
)


def _step_containing(workflow: str, marker: str) -> str:
    marker_index = workflow.index(marker)
    step_start = workflow.rfind("\n      - ", 0, marker_index)
    step_end = workflow.find("\n      - ", marker_index)
    return workflow[step_start : None if step_end == -1 else step_end]


def test_workflow_is_the_single_traffic_weather_monoproject_gate() -> None:
    assert WORKFLOW.is_file()
    assert not LEGACY_WORKFLOW.exists()
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert workflow.startswith("name: Traffic/Weather dbt monoproject pre-merge gate\n")
    pull_request = re.search(
        r"(?ms)^on:\s*\n\s+pull_request:\s*\n(?P<body>.*?)(?=^permissions:)",
        workflow,
    )
    assert pull_request is not None
    assert re.search(
        r"(?m)^\s+branches:\s*\n\s+-\s+dev\s*$", pull_request.group("body")
    )
    assert "paths:" not in pull_request.group("body")
    assert "paths-ignore:" not in pull_request.group("body")
    assert re.search(r"(?m)^  validate-traffic-weather-monoproject:\s*$", workflow)


def test_workflow_runs_shared_checks_for_either_owned_domain() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    scope_step = _step_containing(workflow, "id: scope")

    for token in (
        "domains/traffic/",
        "domains/weather/",
        "models/traffic/",
        "models/weather/",
        "tests/traffic/",
        "tests/weather/",
        "macros/weather/",
        "seeds/weather/",
        "contracts/engine/",
        "analyses/traffic_weather/",
        r"pytest\.ini",
    ):
        assert token in scope_step
    assert 'echo "monoproject_relevant=true" >> "$GITHUB_OUTPUT"' in scope_step
    assert 'echo "traffic_relevant=true" >> "$GITHUB_OUTPUT"' in scope_step

    shared_condition = "steps.scope.outputs.monoproject_relevant == 'true'"
    for marker in (
        "actions/setup-python@v5",
        "Install dbt parser dependencies",
        "Validate repository Python contracts",
        "Resolve root monoproject dependencies",
        "Parse a fresh root monoproject manifest",
        "Validate every named selector is non-empty",
    ):
        assert shared_condition in _step_containing(workflow, marker)

    parse_step = _step_containing(workflow, "Parse a fresh root monoproject manifest")
    assert "dbt parse --no-partial-parse" in parse_step
    assert "--project-dir ." in parse_step
    assert "--profiles-dir ." in parse_step
    assert '--target-path "$RUNNER_TEMP/traffic-weather-monoproject"' in parse_step

    selector_step = _step_containing(
        workflow, "Validate every named selector is non-empty"
    )
    assert "selectors.yml" in selector_step
    assert 'dbt ls --selector "$selector"' in selector_step
    assert "test -n" in selector_step

    pytest_step = _step_containing(workflow, "Validate repository Python contracts")
    assert "ASK_SEOUL_FRESH_MANIFEST" in pytest_step
    assert "python -m pytest -q -p no:cacheprovider" in pytest_step
    assert workflow.index("Parse a fresh root monoproject manifest") < workflow.index(
        "Validate repository Python contracts"
    )
    assert workflow.count("python -m pytest") == 1


def test_traffic_singular_manifest_gate_is_conditionally_narrower() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    singular_step = _step_containing(
        workflow, "Validate Traffic singular-test dependencies"
    )

    assert "steps.scope.outputs.traffic_relevant == 'true'" in singular_step
    assert "steps.scope.outputs.monoproject_relevant == 'true'" not in singular_step
    assert (
        "domains/traffic/contracts/scripts/validate_singular_test_dependency_manifest.py"
        in singular_step
    )
    assert (
        '--manifest "$RUNNER_TEMP/traffic-weather-monoproject/manifest.json"'
        in singular_step
    )
    assert "--tests-root" not in singular_step


def test_workflow_is_parse_only_and_uploads_the_fresh_manifest() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    permissions = re.search(r"(?ms)^permissions:\s*\n(?P<body>.*?)(?=^\S|\Z)", workflow)
    assert permissions is not None
    assert permissions.group("body").strip().splitlines() == ["contents: read"]
    assert "dbt-core==1.10.22" in workflow
    assert "dbt-trino==1.10.2" in workflow
    assert "pytest==8.4.2" in workflow
    assert "python -m pytest -q -p no:cacheprovider" in workflow
    assert "python -m pytest contracts/engine/tests" not in workflow
    assert not re.search(r"(?i)\bdbt\s+(?:test|run|build|seed|snapshot)\b", workflow)
    assert not re.search(r"(?i)\b(?:R2|AWS|TRINO)_[A-Z0-9_]+\b", workflow)

    upload_step = _step_containing(workflow, "actions/upload-artifact@v4")
    assert "always()" in upload_step
    assert "steps.scope.outputs.monoproject_relevant == 'true'" in upload_step
    assert "traffic-weather-monoproject-manifest" in upload_step
    assert "${{ runner.temp }}/traffic-weather-monoproject" in upload_step
    assert "if-no-files-found: ignore" in upload_step
