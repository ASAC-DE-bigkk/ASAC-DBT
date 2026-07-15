from __future__ import annotations

from contracts.engine.tests.fixtures import (
    Path,
    copy,
    json,
    os,
    requires_symlink_capability,
    run_catalog_compare_cli,
    tempfile,
    unittest,
    valid_catalog_pair,
    write_escaped_json_artifact,
    write_json_artifact,
)


class PublicGoldCatalogIoTests(unittest.TestCase):
    def test_strict_catalog_json_limits_and_nonfinite_values_exit_two(self) -> None:
        manifest, catalog = valid_catalog_pair()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manifest_path = write_json_artifact(root, "manifest.json", manifest)
            nonfinite_path = root / "nonfinite.json"
            nonfinite_text = json.dumps(catalog, ensure_ascii=False, sort_keys=True)
            nonfinite_path.write_text(
                nonfinite_text[:-1] + ', "future": NaN}', encoding="utf-8"
            )
            nonfinite_result = run_catalog_compare_cli(
                "--manifest",
                manifest_path,
                "--catalog",
                nonfinite_path,
                "--require-language",
                "ko-KR",
            )
            self.assertEqual(2, nonfinite_result.returncode, nonfinite_result.stdout)
            self.assertEqual(
                "CATALOG_READ_ERROR",
                json.loads(nonfinite_result.stdout)["errors"][0]["code"],
            )
            self.assertNotIn("Traceback", nonfinite_result.stdout)
            self.assertEqual("", nonfinite_result.stderr)

            deep_catalog = copy.deepcopy(catalog)
            nested: dict[str, object] = {}
            deep_catalog["future"] = nested
            for _ in range(70):
                child: dict[str, object] = {}
                nested["next"] = child
                nested = child
            deep_path = write_json_artifact(root, "deep.json", deep_catalog)
            deep_result = run_catalog_compare_cli(
                "--manifest",
                manifest_path,
                "--catalog",
                deep_path,
                "--require-language",
                "ko-KR",
            )
            self.assertEqual(2, deep_result.returncode, deep_result.stdout)
            deep_report = json.loads(deep_result.stdout)
            self.assertEqual("ERROR", deep_report["status"])
            self.assertEqual("JSON_LIMIT_EXCEEDED", deep_report["errors"][0]["code"])
            self.assertEqual("NOT_RUN", deep_report["proof"]["catalog_comparison"])

    def test_comparator_rejects_lone_surrogate_manifest_and_catalog_values_and_keys(
        self,
    ) -> None:
        uid = "model.weather.gold_weather_public_metric"
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            cases = []

            manifest, catalog = valid_catalog_pair()
            manifest["future_surrogate"] = "\ud800"
            cases.append(("manifest_value", manifest, catalog))

            manifest, catalog = valid_catalog_pair()
            manifest["future_mapping"] = {"\ud800": True}
            cases.append(("manifest_key", manifest, catalog))

            manifest, catalog = valid_catalog_pair()
            catalog["nodes"][uid]["columns"]["metric_value"]["type"] = "\ud800"
            cases.append(("catalog_value", manifest, catalog))

            manifest, catalog = valid_catalog_pair()
            catalog["nodes"][uid]["columns"]["\ud800"] = {
                "index": 8,
                "type": "varchar",
            }
            cases.append(("catalog_key", manifest, catalog))

            for name, manifest, catalog in cases:
                with self.subTest(name=name):
                    manifest_path = write_escaped_json_artifact(
                        root, f"manifest-{name}.json", manifest
                    )
                    catalog_path = write_escaped_json_artifact(
                        root, f"catalog-{name}.json", catalog
                    )
                    self.assertTrue(
                        "\\ud800" in manifest_path.read_text(encoding="utf-8")
                        or "\\ud800" in catalog_path.read_text(encoding="utf-8")
                    )
                    output = root / f"report-{name}.json"
                    output.write_text("KEEP", encoding="utf-8")

                    result = run_catalog_compare_cli(
                        "--manifest",
                        manifest_path,
                        "--catalog",
                        catalog_path,
                        "--require-language",
                        "ko-KR",
                        "--output",
                        output,
                    )

                    self.assertEqual(2, result.returncode, result.stdout)
                    report = json.loads(result.stdout)
                    self.assertEqual("ERROR", report["status"])
                    self.assertEqual(
                        ["INVALID_JSON_VALUE"],
                        [error["code"] for error in report["errors"]],
                    )
                    self.assertEqual(
                        result.stdout,
                        result.stdout.encode("utf-8").decode("utf-8"),
                    )
                    self.assertNotIn("\\ud800", result.stdout.casefold())
                    self.assertEqual("KEEP", output.read_text(encoding="utf-8"))
                    self.assertEqual("", result.stderr)
                    self.assertNotIn("Traceback", result.stdout)

    @requires_symlink_capability
    def test_output_is_atomic_and_cannot_alias_either_input(self) -> None:
        manifest, catalog = valid_catalog_pair()
        uid = "model.weather.gold_weather_public_metric"
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manifest_path = write_json_artifact(root, "manifest.json", manifest)
            catalog_path = write_json_artifact(root, "catalog.json", catalog)
            original_manifest = manifest_path.read_bytes()
            original_catalog = catalog_path.read_bytes()

            successful_output = root / "pass-report.json"
            successful = run_catalog_compare_cli(
                "--manifest",
                manifest_path,
                "--catalog",
                catalog_path,
                "--require-language",
                "ko-KR",
                "--output",
                successful_output,
            )
            self.assertEqual(0, successful.returncode, successful.stdout)
            self.assertEqual(
                successful.stdout, successful_output.read_text(encoding="utf-8")
            )

            failing_catalog = copy.deepcopy(catalog)
            failing_catalog["nodes"][uid]["columns"].pop("request_id")
            failing_catalog_path = write_json_artifact(
                root, "failing-catalog.json", failing_catalog
            )
            failing_output = root / "fail-report.json"
            failing = run_catalog_compare_cli(
                "--manifest",
                manifest_path,
                "--catalog",
                failing_catalog_path,
                "--require-language",
                "ko-KR",
                "--output",
                failing_output,
            )
            self.assertEqual(1, failing.returncode, failing.stdout)
            self.assertEqual(failing.stdout, failing_output.read_text(encoding="utf-8"))

            manifest_hard_link = root / "manifest-hard-link.json"
            catalog_hard_link = root / "catalog-hard-link.json"
            os.link(manifest_path, manifest_hard_link)
            os.link(catalog_path, catalog_hard_link)
            manifest_symlink = root / "manifest-symlink.json"
            catalog_symlink = root / "catalog-symlink.json"
            manifest_symlink.symlink_to(manifest_path)
            catalog_symlink.symlink_to(catalog_path)
            collision_outputs = (
                manifest_path,
                catalog_path,
                manifest_hard_link,
                catalog_hard_link,
                manifest_symlink,
                catalog_symlink,
            )
            for output_path in collision_outputs:
                with self.subTest(output=output_path.name):
                    result = run_catalog_compare_cli(
                        "--manifest",
                        manifest_path,
                        "--catalog",
                        catalog_path,
                        "--require-language",
                        "ko-KR",
                        "--output",
                        output_path,
                    )
                    self.assertEqual(2, result.returncode, result.stdout)
                    report = json.loads(result.stdout)
                    self.assertEqual("ERROR", report["status"])
                    self.assertEqual("OUTPUT_WRITE_ERROR", report["errors"][0]["code"])
                    self.assertEqual("PASS", report["proof"]["catalog_comparison"])
                    self.assertEqual("", result.stderr)
                    self.assertNotIn("Traceback", result.stdout)
                    self.assertEqual(original_manifest, manifest_path.read_bytes())
                    self.assertEqual(original_catalog, catalog_path.read_bytes())

            self.assertEqual(
                [],
                sorted(path.name for path in root.glob(".*.tmp")),
            )

    def test_output_failure_preserves_comparison_differences_proof_and_counts(
        self,
    ) -> None:
        manifest, catalog = valid_catalog_pair()
        uid = "model.weather.gold_weather_public_metric"
        catalog["nodes"][uid]["columns"].pop("request_id")
        catalog["nodes"][uid]["columns"]["metric_value"]["type"] = "varchar"
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manifest_path = write_json_artifact(root, "manifest.json", manifest)
            catalog_path = write_json_artifact(root, "catalog.json", catalog)
            original_manifest = manifest_path.read_bytes()
            original_catalog = catalog_path.read_bytes()
            cases = (
                (
                    "invalid_parent_fixture",
                    [],
                    root / "missing-parent" / "report.json",
                    "NOT_RUN",
                ),
                (
                    "catalog_alias_approved",
                    [
                        "--evidence-kind",
                        "approved_dev_catalog",
                        "--evidence-id",
                        "review-144-r1",
                    ],
                    catalog_path,
                    "FAIL",
                ),
            )
            for name, evidence_args, output_path, expected_physical in cases:
                with self.subTest(name=name):
                    common_args = [
                        "--manifest",
                        manifest_path,
                        "--catalog",
                        catalog_path,
                        "--require-language",
                        "ko-KR",
                        *evidence_args,
                    ]
                    baseline_result = run_catalog_compare_cli(*common_args)
                    self.assertEqual(
                        1, baseline_result.returncode, baseline_result.stdout
                    )
                    baseline = json.loads(baseline_result.stdout)
                    self.assertEqual("FAIL", baseline["status"])
                    self.assertEqual(
                        ["INCOMPATIBLE_COLUMN_TYPE", "MISSING_PHYSICAL_COLUMN"],
                        [error["code"] for error in baseline["errors"]],
                    )
                    self.assertEqual(2, baseline["summary"]["difference_count"])
                    self.assertEqual(0, baseline["summary"]["error_count"])
                    self.assertEqual(
                        expected_physical, baseline["proof"]["physical_contract"]
                    )

                    result = run_catalog_compare_cli(
                        *common_args, "--output", output_path
                    )

                    self.assertEqual(2, result.returncode, result.stdout)
                    report = json.loads(result.stdout)
                    self.assertTrue(result.stdout.endswith("\n"))
                    self.assertEqual("ERROR", report["status"])
                    self.assertEqual(baseline["proof"], report["proof"])
                    self.assertEqual(baseline["evidence"], report["evidence"])
                    self.assertEqual(baseline["resources"], report["resources"])
                    self.assertEqual(baseline["errors"], report["errors"][:-1])
                    self.assertEqual("OUTPUT_WRITE_ERROR", report["errors"][-1]["code"])
                    self.assertEqual(2, report["summary"]["difference_count"])
                    self.assertEqual(1, report["summary"]["error_count"])
                    self.assertEqual(
                        baseline["summary"]["resources_checked"],
                        report["summary"]["resources_checked"],
                    )
                    self.assertEqual(original_manifest, manifest_path.read_bytes())
                    self.assertEqual(original_catalog, catalog_path.read_bytes())
                    if name == "invalid_parent_fixture":
                        self.assertFalse(output_path.exists())
                    self.assertEqual("", result.stderr)
                    self.assertNotIn("Traceback", result.stdout)

    @requires_symlink_capability
    def test_symlink_inputs_are_rejected_without_creating_output(self) -> None:
        manifest, catalog = valid_catalog_pair()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manifest_path = write_json_artifact(root, "manifest.json", manifest)
            catalog_path = write_json_artifact(root, "catalog.json", catalog)
            manifest_symlink = root / "manifest-link.json"
            catalog_symlink = root / "catalog-link.json"
            manifest_symlink.symlink_to(manifest_path)
            catalog_symlink.symlink_to(catalog_path)
            for name, selected_manifest, selected_catalog, expected_code in (
                (
                    "manifest",
                    manifest_symlink,
                    catalog_path,
                    "MANIFEST_READ_ERROR",
                ),
                (
                    "catalog",
                    manifest_path,
                    catalog_symlink,
                    "CATALOG_READ_ERROR",
                ),
            ):
                with self.subTest(name=name):
                    output = root / f"{name}-report.json"
                    result = run_catalog_compare_cli(
                        "--manifest",
                        selected_manifest,
                        "--catalog",
                        selected_catalog,
                        "--require-language",
                        "ko-KR",
                        "--output",
                        output,
                    )
                    self.assertEqual(2, result.returncode, result.stdout)
                    report = json.loads(result.stdout)
                    self.assertEqual(expected_code, report["errors"][0]["code"])
                    self.assertEqual("NOT_RUN", report["proof"]["declared_contract"])
                    self.assertFalse(output.exists())
                    self.assertEqual("", result.stderr)


if __name__ == "__main__":
    unittest.main()
