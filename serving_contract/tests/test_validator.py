"""Behavioral oracle for the Serving Contract v1 validator.

Valid fixtures must PASS; invalid fixtures must FAIL with the specific expected
rules. CLI exit codes 0/1/2 are asserted directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from serving_contract.cli import _render_json, main
from serving_contract.model import ServingModel, load_manifest, load_models_from_yaml
from serving_contract.validator import validate

FIXTURES = Path(__file__).parent / "fixtures"
VALID = FIXTURES / "valid_contracts.yml"
INVALID = FIXTURES / "invalid_contracts.yml"
NOT_IN_MANIFEST = FIXTURES / "not_in_manifest.yml"
MANIFEST = FIXTURES / "manifest.json"


def _rules(findings) -> set[str]:
    return {f.rule for f in findings}


def _serving_model(
    *,
    name: str = "gold_projection_fixture",
    serving_overrides: dict | None = None,
    columns: dict | None = None,
    column_contracts: dict | None = None,
) -> ServingModel:
    serving = {
        "enabled": True,
        "external": True,
        "product_id": name.removeprefix("gold_"),
        "product_question": "projection test question",
        "grain": "one row per id",
        "primary_key": ["product_row_id"],
        "publication_mode": "snapshot",
        "zero_policy": "fail",
        "publication_trigger": {"schedule_cron": "0 * * * *"},
    }
    serving.update(serving_overrides or {})
    return ServingModel(
        name=name,
        source="fixture.yml",
        meta={},
        serving=serving,
        columns=columns
        or {
            "product_row_id": ("not_null", "unique"),
            "event_at": (),
            "sample_count": (),
            "public_value": (),
        },
        column_contracts=column_contracts or {},
    )


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
        "usage_pattern_required_missing",
        "usage_pattern_unknown_field",
        "usage_pattern_requires_unknown",
        "usage_pattern_duplicate",
        "usage_pattern_invalid",
        "public_projection_invalid",
        "public_projection_required_field_missing",
        "public_projection_unknown_column",
        "public_projection_internal_field",
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
        ("bad_usage_patterns", "usage_pattern_required_missing"),
        ("bad_usage_patterns", "usage_pattern_unknown_field"),
        ("bad_usage_patterns", "usage_pattern_requires_unknown"),
        ("bad_usage_patterns", "usage_pattern_duplicate"),
        ("bad_usage_patterns", "usage_pattern_invalid"),
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


def test_upsert_strategy_requires_upsert_publication_mode():
    model = ServingModel(
        name="bad_strategy",
        source="test",
        meta={},
        serving={
            "enabled": True,
            "external": False,
            "product_id": "bad_strategy",
            "product_question": "question",
            "grain": "one row per id",
            "primary_key": ["id"],
            "publication_mode": "snapshot",
            "upsert_strategy": "exact_set",
            "zero_policy": "allow",
            "publication_trigger": {"schedule_cron": "0 * * * *"},
        },
        columns={"id": ("not_null", "unique")},
    )

    assert "upsert_strategy_invalid" in _rules(validate([model]).findings)


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


@pytest.mark.parametrize(
    "projection",
    [
        {"schema_version": "1.0", "columns": ["product_row_id"]},
        {"schema_version": "1.0.0", "columns": []},
        {"schema_version": "1.0.0", "columns": ["product_row_id", "product_row_id"]},
        {"schema_version": "1.0.0", "columns": ["product_row_id"], "rename_map": {}},
        {"schema_version": "1.0.0", "columns": ["product_row_id as id"]},
    ],
)
def test_public_projection_rejects_malformed_contracts(projection):
    model = _serving_model(serving_overrides={"public_projection": projection})

    result = validate([model])

    assert "public_projection_invalid" in _rules(result.findings)


def test_public_projection_requires_primary_event_and_reliability_columns():
    model = _serving_model(
        serving_overrides={
            "event_time": "event_at",
            "freshness_slo_minutes": 60,
            "reliability": {
                "sample_count_field": "sample_count",
                "minimum_sample_count": 3,
                "insufficient_sample_policy": "flag_degraded",
            },
            "public_projection": {
                "schema_version": "1.0.0",
                "columns": ["public_value"],
            },
        }
    )

    result = validate([model])

    assert "public_projection_required_field_missing" in _rules(result.findings)


def test_public_projection_rejects_unknown_columns_with_or_without_manifest():
    model = _serving_model(
        serving_overrides={
            "public_projection": {
                "schema_version": "1.0.0",
                "columns": ["product_row_id", "ghost_column"],
            },
        }
    )

    result = validate([model])

    assert "public_projection_unknown_column" in _rules(result.findings)


def test_public_projection_rejects_internal_or_secret_columns():
    model = _serving_model(
        serving_overrides={
            "public_projection": {
                "schema_version": "1.0.0",
                "columns": ["product_row_id", "representative_dag_run_id", "api_token"],
            },
        },
        columns={
            "product_row_id": ("not_null", "unique"),
            "representative_dag_run_id": (),
            "api_token": (),
        },
    )

    result = validate([model])

    assert "public_projection_internal_field" in _rules(result.findings)


def test_public_projection_rejects_not_null_column_declared_nullable():
    model = _serving_model(
        serving_overrides={
            "public_projection": {
                "schema_version": "1.0.0",
                "columns": ["product_row_id"],
            },
        },
        columns={"product_row_id": ("not_null", "unique")},
        column_contracts={
            "product_row_id": {
                "name": "product_row_id",
                "description": "public row identifier",
                "data_type": "varchar",
                "config": {
                    "meta": {
                        "semantic_role": "primary_key",
                        "nullable": True,
                        "null_meaning": "null means the identifier is unavailable",
                        "unit": "not_applicable",
                    }
                },
            }
        },
    )

    result = validate([model])

    assert "public_projection_nullability_conflict" in _rules(result.findings)


def test_projection_identity_hash_preserves_order_and_ignores_descriptions():
    from serving_contract.projection_identity import canonical_projection_bytes, projection_schema_hash

    projection = {
        "schema_version": "1.0.0",
        "columns": ["product_row_id", "value"],
    }
    columns = {
        "product_row_id": {
            "description": "first wording",
            "data_type": "VARCHAR",
            "config": {
                "meta": {
                    "nullable": False,
                    "unit": "not_applicable",
                    "semantic_role": "primary_key",
                }
            },
        },
        "value": {
            "description": "measurement wording",
            "data_type": "DOUBLE",
            "config": {
                "meta": {
                    "nullable": True,
                    "unit": "km/h",
                    "semantic_role": "metric",
                }
            },
        },
    }

    first_bytes = canonical_projection_bytes(projection, columns)
    second_bytes = canonical_projection_bytes(projection, {**columns, "value": {**columns["value"], "description": "changed"}})
    reordered = {**projection, "columns": ["value", "product_row_id"]}

    assert first_bytes == second_bytes
    assert projection_schema_hash(projection, columns) == projection_schema_hash(projection, columns)
    assert projection_schema_hash(projection, columns) != projection_schema_hash(reordered, columns)
    assert projection_schema_hash(projection, columns) != projection_schema_hash(
        projection,
        {
            **columns,
            "value": {
                **columns["value"],
                "data_type": "DECIMAL(10,2)",
            },
        },
    )
