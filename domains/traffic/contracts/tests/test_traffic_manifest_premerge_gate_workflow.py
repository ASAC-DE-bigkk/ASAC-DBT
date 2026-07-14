from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "traffic-manifest-premerge-gate.yml"


class TrafficManifestPremergeGateWorkflowTest(unittest.TestCase):
    @staticmethod
    def _step_containing(workflow: str, marker: str) -> str:
        marker_index = workflow.index(marker)
        step_start = workflow.rfind("\n      - ", 0, marker_index)
        step_end = workflow.find("\n      - ", marker_index)
        return workflow[step_start : None if step_end == -1 else step_end]

    def test_workflow_always_starts_for_dev_pull_requests(self) -> None:
        self.assertTrue(
            WORKFLOW.is_file(),
            f"Traffic manifest pre-merge workflow is missing: {WORKFLOW}",
        )
        workflow = WORKFLOW.read_text(encoding="utf-8")

        pull_request = re.search(
            r"(?ms)^on:\s*\n\s+pull_request:\s*\n(?P<body>.*?)(?=^permissions:)",
            workflow,
        )
        self.assertIsNotNone(pull_request)
        self.assertRegex(
            pull_request.group("body"),
            r"(?m)^\s+branches:\s*\n\s+-\s+dev\s*$",
        )
        self.assertNotIn("paths:", pull_request.group("body"))
        self.assertNotIn("paths-ignore:", pull_request.group("body"))
        self.assertRegex(workflow, r"(?m)^  validate-traffic-manifest:\s*$")

        job = re.search(
            r"(?ms)^  validate-traffic-manifest:\s*\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:\s*$|\Z)",
            workflow,
        )
        self.assertIsNotNone(job)
        self.assertNotRegex(job.group("body"), r"(?m)^    if:\s*")

    def test_workflow_scopes_runner_to_traffic_relevant_changes(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertRegex(workflow, r"(?m)^\s+id: scope\s*$")
        self.assertIn(
            "BASE_SHA: ${{ github.event.pull_request.base.sha }}",
            workflow,
        )
        self.assertIn(
            "HEAD_SHA: ${{ github.event.pull_request.head.sha }}",
            workflow,
        )
        self.assertIn(
            'changed_files="$(git diff --name-only "$BASE_SHA" "$HEAD_SHA")"',
            workflow,
        )
        self.assertIn(
            "grep -Eq '^(domains/traffic/|packages/asac_axes/|\\.github/workflows/traffic-manifest-premerge-gate\\.yml$)'",
            workflow,
        )
        self.assertIn('echo "traffic_relevant=true" >> "$GITHUB_OUTPUT"', workflow)
        self.assertIn('echo "traffic_relevant=false" >> "$GITHUB_OUTPUT"', workflow)

        scope_step = self._step_containing(workflow, "id: scope")
        self.assertNotIn("domains/weather/", scope_step)

        relevant_condition = "steps.scope.outputs.traffic_relevant == 'true'"
        for marker in (
            "actions/setup-python@v5",
            "Install dbt parser dependencies",
            "Validate fresh Traffic manifest dependencies",
        ):
            self.assertIn(relevant_condition, self._step_containing(workflow, marker))

        skip_step = self._step_containing(workflow, "Skip Traffic manifest validation")
        self.assertIn(
            "steps.scope.outputs.traffic_relevant != 'true'",
            skip_step,
        )

        upload_step = self._step_containing(workflow, "actions/upload-artifact@v4")
        self.assertIn("always()", upload_step)
        self.assertIn(relevant_condition, upload_step)
        self.assertIn("${{ runner.temp }}/traffic-manifest-gate", upload_step)
        self.assertIn("if-no-files-found: ignore", upload_step)

    def test_workflow_remains_a_read_only_manifest_gate(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")

        permissions_match = re.search(
            r"(?ms)^permissions:\s*\n(?P<body>.*?)(?=^\S|\Z)",
            workflow,
        )
        self.assertIsNotNone(permissions_match)
        self.assertEqual(
            permissions_match.group("body").strip().splitlines(),
            ["contents: read"],
        )

        checkout_step = self._step_containing(workflow, "actions/checkout@v4")
        self.assertRegex(checkout_step, r"(?m)^\s+fetch-depth:\s*0\s*$")

        self.assertIn("actions/setup-python@v5", workflow)
        self.assertRegex(workflow, r"(?m)^\s*python-version:\s*['\"]?3\.11['\"]?\s*$")
        self.assertIn("dbt-core==1.10.22", workflow)
        self.assertIn("dbt-trino==1.10.2", workflow)

        self.assertIn(
            "domains/traffic/contracts/scripts/run_traffic_manifest_premerge_gate.py",
            workflow,
        )
        self.assertIn("--project-dir domains/traffic", workflow)
        self.assertIn('--target-path "$RUNNER_TEMP/traffic-manifest-gate"', workflow)

        self.assertNotRegex(
            workflow,
            r"(?i)\bdbt\s+(?:test|run|build|seed|snapshot)\b",
        )
        self.assertNotRegex(workflow, r"(?i)\b(?:R2|AWS|TRINO)_[A-Z0-9_]+\b")


if __name__ == "__main__":
    unittest.main()
