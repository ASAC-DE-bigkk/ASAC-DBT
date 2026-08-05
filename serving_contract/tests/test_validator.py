"""Behavioral oracle for the Serving Contract v1 validator.

Valid fixtures must PASS; invalid fixtures must FAIL with the specific expected
rules. CLI exit codes 0/1/2 are asserted directly.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from serving_contract.cli import _render_json, main
from serving_contract.model import ServingModel, load_manifest, load_models_from_yaml
from serving_contract.validator import validate

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[2]
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
            "collected_at": (),
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


def test_public_projection_requires_explicit_freshness_field():
    model = _serving_model(
        serving_overrides={
            "event_time": "event_at",
            "freshness_field": "collected_at",
            "freshness_slo_minutes": 60,
            "public_projection": {
                "schema_version": "1.0.0",
                "columns": ["product_row_id", "event_at"],
            },
        }
    )

    result = validate([model])

    assert any(
        finding.rule == "public_projection_required_field_missing"
        and "collected_at" in finding.message
        for finding in result.findings
    )


def test_freshness_field_must_be_a_model_column():
    model = _serving_model(
        serving_overrides={
            "freshness_field": "missing_collected_at",
            "freshness_slo_minutes": 60,
        }
    )

    result = validate([model])

    assert "freshness_field_not_a_column" in _rules(result.findings)


def test_freshness_field_requires_freshness_slo():
    model = _serving_model(
        serving_overrides={"freshness_field": "collected_at"}
    )

    result = validate([model])

    assert any(
        finding.rule == "conditional_required_missing"
        and "freshness_field" in finding.message
        for finding in result.findings
    )


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


def test_source_evidence_rejects_missing_or_ambiguous_rights_declaration():
    model = _serving_model(
        serving_overrides={
            "source_evidence": [
                {
                    "source_id": "kma_vilage_fcst",
                    "source_url": "http://not-secure.example.test/kma",
                    "license": "",
                    "license_url": "https://example.test/kogl",
                    "redistribution": "maybe",
                    "attribution": "",
                    "rights_checked_at": "2026/08/04",
                    "unexpected": "typo-must-not-pass",
                },
                {
                    "source_id": "kma_vilage_fcst",
                    "source_url": "https://example.test/duplicate",
                    "license": "KOGL-1",
                    "license_url": "https://example.test/kogl",
                    "redistribution": "allowed_with_attribution",
                    "attribution": "기상청",
                    "rights_checked_at": "2026-08-04",
                },
            ],
        }
    )

    result = validate([model])

    rules = _rules(result.findings)
    assert "source_evidence_invalid" in rules
    assert "source_evidence_unknown_field" in rules
    assert "source_evidence_duplicate" in rules


def test_quality_coverage_rejects_unknown_field_and_unachievable_threshold():
    model = _serving_model(
        serving_overrides={
            "quality_coverage": {
                "field": "missing_dimension",
                "expected_distinct_count": 0,
                "minimum_ratio": 1.2,
                "unexpected": "typo-must-not-pass",
            },
        }
    )

    result = validate([model])

    rules = _rules(result.findings)
    assert "quality_coverage_invalid" in rules
    assert "quality_coverage_unknown_field" in rules


def test_quality_coverage_allows_source_relation_measurement_outside_public_projection():
    model = _serving_model(
        serving_overrides={
            "public_projection": {
                "schema_version": "1.0.0",
                "columns": ["product_row_id", "event_at"],
            },
            "quality_coverage": {
                "field": "source_dimension",
                "expected_distinct_count": 152,
                "minimum_ratio": 1.0,
                "measurement_scope": "source_relation",
            },
        },
        columns={
            "product_row_id": ("not_null", "unique"),
            "event_at": (),
            "source_dimension": (),
        },
    )

    result = validate([model])

    assert not {"quality_coverage_invalid", "quality_coverage_unknown_field"} & _rules(result.findings)


def test_quality_coverage_allows_explicit_not_applicable_reason():
    model = _serving_model(
        serving_overrides={
            "quality_coverage": {
                "not_applicable_reason": "게시 모집단이 매 source run의 최근 유효 관측 집합으로 동적으로 정의됨",
            }
        }
    )

    result = validate([model])

    assert "quality_coverage_invalid" not in _rules(result.findings)


def test_public_projection_uses_public_primary_key_for_rollup_grain():
    model = _serving_model(
        serving_overrides={
            "primary_key": ["product_row_id", "source_dimension"],
            "public_primary_key": ["product_row_id"],
            "public_projection": {
                "schema_version": "1.0.0",
                "columns": ["product_row_id", "event_at"],
            },
        },
        columns={
            "product_row_id": ("not_null", "unique"),
            "source_dimension": ("not_null",),
            "event_at": (),
        },
    )

    result = validate([model])

    required_missing = [f for f in result.findings if f.rule == "public_projection_required_field_missing"]
    assert not required_missing


def test_public_primary_key_requires_public_projection():
    model = _serving_model(
        serving_overrides={
            "public_primary_key": ["product_row_id"],
        }
    )

    result = validate([model])

    assert "public_projection_invalid" in _rules(result.findings)


def test_citydata_and_transit_declared_source_evidence_is_complete_and_valid():
    """Citydata's source/coverage and Transit's source evidence retain their declared contracts."""
    models = load_models_from_yaml(
        [
            REPO_ROOT / "domains/citydata/models/gold/_citydata_gold__models.yml",
            REPO_ROOT / "domains/transit/models/schema.yml",
        ]
    )
    by_name = {model.name: model for model in models}
    citydata = by_name["gold_citydata_purchasing_power_daily"]
    transit = by_name["gold_transit_parking_full_risk"]

    assert citydata.serving["source_evidence"] == [
        {
            "source_id": "seoul_citydata",
            "source_url": "https://data.seoul.go.kr/dataList/OA-21285/F/1/datasetView.do",
            "license": "공공누리 제1유형(출처표시)",
            "license_url": "https://www.kogl.or.kr/info/licenseType1.do",
            "redistribution": "allowed_with_attribution",
            "attribution": "서울특별시",
            "rights_checked_at": "2026-08-03",
        }
    ]
    assert citydata.serving["quality_coverage"] == {
        "field": "area_cd",
        "expected_distinct_count": 121,
        "minimum_ratio": 1.0,
    }
    assert transit.serving["source_evidence"] == [
        {
            "source_id": "park_info_master",
            "source_url": "https://data.seoul.go.kr/dataList/OA-13122/S/1/datasetView.do",
            "license": "공공누리 제1유형(출처표시)",
            "license_url": "https://www.kogl.or.kr/info/licenseType1.do",
            "redistribution": "allowed_with_attribution",
            "attribution": "서울특별시",
            "rights_checked_at": "2026-08-03",
        },
        {
            "source_id": "parking",
            "source_url": "https://data.seoul.go.kr/dataList/OA-21709/A/1/datasetView.do",
            "license": "공공누리 제1유형(출처표시)",
            "license_url": "https://www.kogl.or.kr/info/licenseType1.do",
            "redistribution": "allowed_with_attribution",
            "attribution": "서울특별시",
            "rights_checked_at": "2026-08-03",
        },
    ]

    result = validate([citydata, transit])
    assert result.ok, [finding.as_dict() for finding in result.findings]


def test_commerce_localdata_source_evidence_covers_all_registry_sources():
    """Commerce preserves one static rights record for every LOCALDATA registry source."""
    models = load_models_from_yaml(
        [REPO_ROOT / "domains/commerce/models/gold/_commerce_gold__models.yml"]
    )
    commerce = {model.name: model for model in models}["gold_license_flow_monthly"]
    sources = commerce.serving["source_evidence"]

    with (
        REPO_ROOT / "domains/commerce/seeds/commerce_dataset_taxonomy.csv"
    ).open(encoding="utf-8-sig", newline="") as handle:
        expected_source_ids = {
            f"commerce_localdata_{row['short']}" for row in csv.DictReader(handle)
        }

    assert len(expected_source_ids) == 152
    assert len(sources) == 152
    assert {source["source_id"] for source in sources} == expected_source_ids
    assert len({source["source_url"] for source in sources}) == 152
    assert all(
        source["source_url"].startswith("https://data.seoul.go.kr/dataList/OA-")
        and source["source_url"].endswith("/S/1/datasetView.do")
        for source in sources
    )
    assert {source["license_url"] for source in sources} == {
        "https://www.kogl.or.kr/info/licenseType1.do"
    }
    assert {source["redistribution"] for source in sources} == {
        "allowed_with_attribution"
    }
    assert {source["rights_checked_at"] for source in sources} == {"2026-08-04"}
    assert len({source["license"] for source in sources}) == 1
    assert len({source["attribution"] for source in sources}) == 1

    result = validate([commerce])
    assert result.ok, [finding.as_dict() for finding in result.findings]


def test_culture_activity_source_evidence_covers_all_six_lineages_with_approved_redistribution():
    """Culture records every lineage with approved external redistribution."""
    models = load_models_from_yaml(
        [REPO_ROOT / "domains/culture/models/gold/_culture_gold__models.yml"]
    )
    culture = {model.name: model for model in models}["gold_culture_activity_by_dong"]

    assert culture.serving["source_evidence"] == [
        {
            "source_id": "kopis_open_api",
            "source_url": "https://www.kopis.or.kr/por/cs/openapi/openApiFaq.do?menuId=MNU_00074",
            "license": "KOPIS Open API 2차 가공 집계의 외부 API 재배포·출처표시 허용",
            "license_url": "https://kopis.or.kr/upload/openApi/%EA%B3%B5%EC%97%B0%EC%98%88%EC%88%A0%ED%86%B5%ED%95%A9%EC%A0%84%EC%82%B0%EB%A7%9DOpenAPI%EA%B0%9C%EB%B0%9C%EA%B0%80%EC%9D%B4%EB%93%9C.pdf",
            "redistribution": "allowed_with_attribution",
            "attribution": "공연예술통합전산망(KOPIS)",
            "rights_checked_at": "2026-08-04",
        },
        {
            "source_id": "seoul_cultural_event",
            "source_url": "https://data.seoul.go.kr/dataList/OA-15486/S/1/datasetView.do",
            "license": "공공누리 제1유형(출처표시)",
            "license_url": "https://www.kogl.or.kr/info/licenseType1.do",
            "redistribution": "allowed_with_attribution",
            "attribution": "서울특별시",
            "rights_checked_at": "2026-08-04",
        },
        {
            "source_id": "sema_exhibition",
            "source_url": "https://data.seoul.go.kr/dataList/OA-15323/S/1/datasetView.do",
            "license": "공공누리 제1유형(출처표시)",
            "license_url": "https://www.kogl.or.kr/info/licenseType1.do",
            "redistribution": "allowed_with_attribution",
            "attribution": "서울시립미술관",
            "rights_checked_at": "2026-08-04",
        },
        {
            "source_id": "sejong_performance",
            "source_url": "https://data.seoul.go.kr/dataList/OA-2708/S/1/datasetView.do",
            "license": "공공누리 제1유형(출처표시)",
            "license_url": "https://www.kogl.or.kr/info/licenseType1.do",
            "redistribution": "allowed_with_attribution",
            "attribution": "세종문화회관, 각 컨텐츠주체",
            "rights_checked_at": "2026-08-04",
        },
        {
            "source_id": "kcisa_culture_info",
            "source_url": "https://www.data.go.kr/data/15138937/openapi.do",
            "license": "이용허락범위 제한 없음",
            "license_url": "https://www.data.go.kr/data/15138937/openapi.do",
            "redistribution": "allowed_with_attribution",
            "attribution": "한국문화정보원",
            "rights_checked_at": "2026-08-04",
        },
        {
            "source_id": "national_data_office_admin_dong_link",
            "source_url": "https://www.data.go.kr/data/15136368/fileData.do",
            "license": "공공저작물 제3유형(출처표시·변경금지) — 2차 가공 집계 외부 API 재배포 승인",
            "license_url": "https://www.kogl.or.kr/info/licenseType3.do",
            "redistribution": "allowed_with_attribution",
            "attribution": "국가데이터처",
            "rights_checked_at": "2026-08-04",
        },
    ]
    assert {source["redistribution"] for source in culture.serving["source_evidence"]} == {
        "allowed_with_attribution"
    }

    result = validate([culture])
    assert result.ok, [finding.as_dict() for finding in result.findings]


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
