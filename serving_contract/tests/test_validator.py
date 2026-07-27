"""Behavioral oracle for the Serving Contract v1 validator.

Valid fixtures must PASS; invalid fixtures must FAIL with the specific expected
rules. CLI exit codes 0/1/2 are asserted directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from serving_contract.cli import _render_json, main
from serving_contract.model import load_manifest, load_models_from_yaml
from serving_contract.validator import validate

FIXTURES = Path(__file__).parent / "fixtures"
VALID = FIXTURES / "valid_contracts.yml"
INVALID = FIXTURES / "invalid_contracts.yml"
NOT_IN_MANIFEST = FIXTURES / "not_in_manifest.yml"
MANIFEST = FIXTURES / "manifest.json"


def _rules(findings) -> set[str]:
    return {f.rule for f in findings}


def test_valid_contracts_pass_with_manifest():
    models = load_models_from_yaml([VALID])
    result = validate(models, load_manifest(MANIFEST))
    assert result.ok, [f.as_dict() for f in result.findings]
    assert result.models_checked == 2


def test_valid_contracts_pass_without_manifest():
    models = load_models_from_yaml([VALID])
    result = validate(models)  # no manifest => membership/column checks fall back to yml
    assert result.ok, [f.as_dict() for f in result.findings]


def test_invalid_contracts_fail_with_expected_rules():
    models = load_models_from_yaml([INVALID])
    result = validate(models)
    assert not result.ok
    rules = _rules(result.findings)
    expected = {
        "required_field_missing",
        "external_enabled_conflict",
        "invalid_enum_value",
        "primary_key_not_a_column",
        "primary_key_evidence_missing",
        "excluded_field_present",
        "legacy_double_declaration",
        "publication_trigger_invalid",
        "invalid_field_format",
        "partial_policy_invalid",
        "reliability_invalid",
        "product_id_duplicate",
        "conditional_required_missing",
    }
    missing = expected - rules
    assert not missing, f"expected rules not raised: {missing}"


@pytest.mark.parametrize(
    "model_name,rule",
    [
        ("bad_missing_required", "required_field_missing"),
        ("bad_external_conflict", "external_enabled_conflict"),
        ("bad_enum", "invalid_enum_value"),
        ("bad_primary_key", "primary_key_not_a_column"),
        ("bad_excluded", "excluded_field_present"),
        ("bad_double_decl", "legacy_double_declaration"),
        ("bad_trigger", "publication_trigger_invalid"),
        ("bad_pid_format", "invalid_field_format"),
        ("bad_partial", "partial_policy_invalid"),
        ("bad_reliability", "reliability_invalid"),
        ("bad_missing_freshness_slo", "conditional_required_missing"),
    ],
)
def test_specific_rule_attaches_to_model(model_name, rule):
    models = load_models_from_yaml([INVALID])
    result = validate(models)
    hits = [f for f in result.findings if f.model == model_name and f.rule == rule]
    assert hits, f"{model_name} should raise {rule}; got {[f.as_dict() for f in result.findings if f.model == model_name]}"


def test_model_not_in_manifest_only_with_manifest():
    models = load_models_from_yaml([NOT_IN_MANIFEST])
    # Without a manifest the rule must not fire.
    assert "model_not_in_manifest" not in _rules(validate(models).findings)
    # With a manifest that lacks the model, it fires.
    result = validate(models, load_manifest(MANIFEST))
    assert "model_not_in_manifest" in _rules(result.findings)


def test_cli_exit_codes():
    assert main(["--source", str(VALID), "--manifest", str(MANIFEST)]) == 0  # PASS
    assert main(["--source", str(INVALID)]) == 1  # FAIL
    assert main(["--source", str(FIXTURES / "does_not_exist_*.yml")]) == 2  # ERROR (no match)


def test_json_report_is_deterministic_utf8():
    result = validate(load_models_from_yaml([INVALID]))
    first = _render_json(result)
    second = _render_json(result)
    assert first == second  # sorted keys + sorted findings => byte-stable
    assert first.encode("utf-8")  # Korean messages encode cleanly
    assert "product_id_duplicate" in first
