from __future__ import annotations

from contracts.engine.tests.fixtures import (
    manifest_validator_module,
    unittest,
    valid_manifest,
    valid_manifest_node,
)


class PublicGoldManifestExposureTimestampTests(unittest.TestCase):
    def test_exposure_timestamp_detector_covers_naive_and_compact_offsets_without_version_false_positive(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_served"
        cases = (
            ("naive", "name", "application-2026-07-12T12:34:56", ".name"),
            (
                "compact_offset",
                "type",
                "app-2026-07-12T12:34:56.123+0900-live",
                ".type",
            ),
        )
        for name, field, value, suffix in cases:
            with self.subTest(name=name):
                manifest = valid_manifest(
                    (uid, valid_manifest_node(uid, visibility="served"))
                )
                exposure_uid = next(iter(manifest["exposures"]))
                manifest["exposures"][exposure_uid][field] = value
                report, catalog = validator.validate_manifest(manifest)
                self.assertEqual("FAIL", report["status"], report)
                self.assertIsNone(catalog)
                self.assertIn(
                    f"exposures.{exposure_uid}{suffix}",
                    [error["path"] for error in report["errors"]],
                )

        valid = valid_manifest((uid, valid_manifest_node(uid, visibility="served")))
        valid_uid = next(iter(valid["exposures"]))
        valid["exposures"][valid_uid]["name"] = "application-v2026.07.12-123456"
        valid_report, valid_catalog = validator.validate_manifest(valid)
        self.assertEqual("PASS", valid_report["status"], valid_report)
        self.assertIsNotNone(valid_catalog)


if __name__ == "__main__":
    unittest.main()
