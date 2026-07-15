from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
WORKFLOW = (
    REPOSITORY_ROOT
    / ".github"
    / "workflows"
    / "traffic-weather-monoproject-premerge-gate.yml"
)
WORKFLOW_MODULE = PROJECT_ROOT / "workflows" / "premerge_gate.py"
CI_REQUIREMENTS = PROJECT_ROOT / "workflows" / "requirements-ci.txt"
LEGACY_WORKFLOW = (
    REPOSITORY_ROOT / ".github" / "workflows" / "traffic-manifest-premerge-gate.yml"
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


def test_root_workflow_is_only_a_github_discovery_adapter() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert WORKFLOW_MODULE.is_file()
    assert CI_REQUIREMENTS.is_file()

    scope_step = _step_containing(workflow, "id: scope")
    assert "python domains/traffic_weather/workflows/premerge_gate.py scope" in scope_step
    assert '--github-output "$GITHUB_OUTPUT"' in scope_step
    assert workflow.index("id: scope") < workflow.index("actions/setup-python@v5")

    shared_condition = "steps.scope.outputs.monoproject_relevant == 'true'"
    for marker in (
        "actions/setup-python@v5",
        "Install project gate dependencies",
        "Run domain-owned pre-merge workflow",
    ):
        assert shared_condition in _step_containing(workflow, marker)

    install_step = _step_containing(workflow, "Install project gate dependencies")
    assert "working-directory: domains/traffic_weather" in install_step
    assert "python -m pip install -r workflows/requirements-ci.txt" in install_step

    gate_step = _step_containing(workflow, "Run domain-owned pre-merge workflow")
    assert "working-directory: domains/traffic_weather" in gate_step
    assert "python -m workflows.premerge_gate run" in gate_step
    assert "--repository-root ../.." in gate_step
    assert "--project-dir ." in gate_step
    assert 'BASE_SHA: ${{ github.event.pull_request.base.sha }}' in gate_step
    assert 'HEAD_SHA: ${{ github.event.pull_request.head.sha }}' in gate_step

    forbidden_implementation = (
        "git diff",
        "monoproject_pattern",
        "dbt deps",
        "dbt parse",
        "dbt ls",
        "python -m pytest",
        "validate_singular_test_dependency_manifest.py",
        "packages/asac_axes/",
    )
    assert all(token not in workflow for token in forbidden_implementation)


def test_workflow_is_parse_only_and_uploads_the_optional_fresh_manifest() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    permissions = re.search(r"(?ms)^permissions:\s*\n(?P<body>.*?)(?=^\S|\Z)", workflow)
    assert permissions is not None
    assert permissions.group("body").strip().splitlines() == ["contents: read"]
    assert not re.search(r"(?i)\bdbt\s+(?:test|run|build|seed|snapshot)\b", workflow)
    assert not re.search(r"(?i)\b(?:R2|AWS|TRINO)_[A-Z0-9_]+\b", workflow)

    requirements = CI_REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    assert requirements == [
        "dbt-core==1.10.22",
        "dbt-trino==1.10.2",
        "pytest==8.4.2",
    ]

    upload_step = _step_containing(workflow, "actions/upload-artifact@v4")
    assert "always()" in upload_step
    assert "steps.scope.outputs.monoproject_relevant == 'true'" in upload_step
    assert "traffic-weather-monoproject-manifest" in upload_step
    assert "${{ runner.temp }}/traffic-weather-monoproject" in upload_step
    assert "if-no-files-found: ignore" in upload_step
