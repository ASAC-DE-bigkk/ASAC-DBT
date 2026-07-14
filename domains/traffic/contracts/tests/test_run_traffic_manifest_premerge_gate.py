from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


TEST_ROOT = Path(tempfile.gettempdir()) / "traffic-manifest-premerge-gate-unit"


class RunTrafficManifestPremergeGateTest(unittest.TestCase):
    def setUp(self) -> None:
        from domains.traffic.contracts.scripts import (
            run_traffic_manifest_premerge_gate as runner,
        )

        self.runner = runner

    def test_run_gate_resolves_dependencies_parses_fresh_manifest_and_validates_it(
        self,
    ) -> None:
        project_dir = TEST_ROOT / "project"
        target_path = TEST_ROOT / ".tmp" / "traffic-manifest-target"
        snapshot_run_id = "ci__traffic-manifest-premerge-gate"

        with patch.object(self.runner.subprocess, "run") as run:
            self.runner.run_gate(
                project_dir=project_dir,
                dbt_bin="dbt",
                target_path=target_path,
                snapshot_run_id=snapshot_run_id,
            )

        self.assertEqual(run.call_count, 3)
        deps_call, parse_call, validator_call = run.call_args_list
        self.assertEqual(deps_call.args[0], ["dbt", "deps"])
        self.assertNotIn("--target-path", deps_call.args[0])

        parse_command = parse_call.args[0]
        self.assertEqual(
            parse_command[:7],
            [
                "dbt",
                "parse",
                "--no-partial-parse",
                "--target",
                "dev",
                "--target-path",
                str(target_path),
            ],
        )
        vars_index = parse_command.index("--vars")
        self.assertEqual(
            json.loads(parse_command[vars_index + 1]),
            {"traffic_snapshot_dag_run_id": snapshot_run_id},
        )

        self.assertEqual(
            validator_call.args[0],
            [
                sys.executable,
                str(self.runner.VALIDATOR_SCRIPT),
                "--manifest",
                str(target_path / "manifest.json"),
            ],
        )

        for dbt_call in (deps_call, parse_call):
            self.assertEqual(dbt_call.kwargs["cwd"], project_dir)
            self.assertTrue(dbt_call.kwargs["check"])
            environment = dbt_call.kwargs["env"]
            self.assertEqual(environment["DBT_PROJECT_DIR"], str(project_dir))
            self.assertEqual(environment["DBT_PROFILES_DIR"], str(project_dir))
            self.assertEqual(environment["DBT_TARGET"], "dev")

    def test_cli_uses_synthetic_snapshot_run_id_by_default(self) -> None:
        project_dir = TEST_ROOT / "project"
        target_path = TEST_ROOT / ".tmp" / "traffic-manifest-target"

        with patch.object(self.runner, "run_gate") as run_gate:
            result = self.runner.main(
                [
                    "--project-dir",
                    str(project_dir),
                    "--dbt-bin",
                    "custom-dbt",
                    "--target-path",
                    str(target_path),
                ]
            )

        self.assertEqual(result, 0)
        run_gate.assert_called_once_with(
            project_dir=project_dir,
            dbt_bin="custom-dbt",
            target_path=target_path,
            snapshot_run_id="ci__traffic-manifest-premerge-gate",
        )

    def test_run_gate_propagates_the_first_subprocess_failure(self) -> None:
        failure = subprocess.CalledProcessError(1, ["dbt", "deps"])

        with patch.object(self.runner.subprocess, "run", side_effect=failure) as run:
            with self.assertRaisesRegex(subprocess.CalledProcessError, "dbt"):
                self.runner.run_gate(
                    project_dir=TEST_ROOT / "project",
                    dbt_bin="dbt",
                    target_path=TEST_ROOT / ".tmp" / "traffic-manifest-target",
                    snapshot_run_id="ci__traffic-manifest-premerge-gate",
                )

        self.assertEqual(run.call_count, 1)

    def test_run_gate_resolves_relative_project_and_target_paths_from_caller_cwd(
        self,
    ) -> None:
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            os.chdir(workspace)
            try:
                with patch.object(self.runner.subprocess, "run") as run:
                    self.runner.run_gate(
                        project_dir=Path("."),
                        dbt_bin="dbt",
                        target_path=Path(".tmp/traffic-manifest-target"),
                        snapshot_run_id="ci__traffic-manifest-premerge-gate",
                    )
            finally:
                os.chdir(original_cwd)

        project_dir = workspace
        target_path = workspace / ".tmp" / "traffic-manifest-target"
        deps_call, parse_call, validator_call = run.call_args_list
        self.assertEqual(deps_call.kwargs["cwd"], project_dir)
        self.assertEqual(deps_call.kwargs["env"]["DBT_PROJECT_DIR"], str(project_dir))
        self.assertEqual(deps_call.kwargs["env"]["DBT_PROFILES_DIR"], str(project_dir))
        self.assertEqual(parse_call.kwargs["cwd"], project_dir)
        self.assertEqual(parse_call.args[0][6], str(target_path))
        self.assertEqual(validator_call.args[0][-1], str(target_path / "manifest.json"))


if __name__ == "__main__":
    unittest.main()
