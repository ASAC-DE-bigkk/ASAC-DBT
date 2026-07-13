from __future__ import annotations

import copy
import importlib
import io
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from domains.weather.contracts.scripts import lint_schema_contract_source as lint


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = (
    REPO_ROOT
    / "domains"
    / "weather"
    / "contracts"
    / "scripts"
    / "lint_schema_contract_source.py"
)
MANIFEST_SCRIPT = (
    REPO_ROOT
    / "domains"
    / "weather"
    / "contracts"
    / "scripts"
    / "validate_public_gold_manifest.py"
)
CATALOG_COMPARE_SCRIPT = (
    REPO_ROOT
    / "domains"
    / "weather"
    / "contracts"
    / "scripts"
    / "compare_public_gold_catalog.py"
)
OWNER_MISSING = object()
CANONICAL_TIMEZONE = "Asia/Seoul"
CANONICAL_SPACE_APPROVED_REVISION_DATE = "2025-04-01"
CANONICAL_SPACE_SOURCE_CHAIN = [
    "iceberg_dev.common.bronze_admin_dong_master",
    "asac_axes.dim_admin_dong",
]
CANONICAL_SPACE_STAMP = [
    "admin_dong_code",
    "admin_dong",
    "gu_code",
    "gu",
    "admin_dong_revision_date",
]
BASE_COLUMN_ORDER = [
    "district_id",
    "metric_value",
    "dag_run_id",
    "product_as_of_at",
    "published_at",
    "raw_object_key",
    "request_id",
]


VALID_MIXED_SCHEMA = """
version: 2
models:
  - name: gold_weather_orders
    description: 주문 골드 모델
    config:
      contract:
        enforced: true
    columns:
      - name: order_id
        description: "주문 식별자 `order_id`"
        data_tests:
          - accepted_values:
              arguments:
                values: ['A', 'B'] # scalar flow list
  - name: quoted_model
    description: '인용 모델 설명 # 따옴표 안 주석 문자'
    columns:
      - name: metric_value
        description: |2-
          지표 값입니다.
          `metric_value` 코드를 보존합니다.
seeds:
  - name: area_seed
    description: >-
      서울 지역 코드
      기준표입니다.
    columns:
      - name: area_code
        description: 서울 지역 코드 # 실제 주석
sources:
  - name: public_api
    description: "서울 공공 API {{ target.database }}"
    database: "{{ target.database }}"
    freshness:
      warn_after: {count: 30, period: hour}
    tables:
      - name: events
        description: 사건 원천 테이블
        columns:
          - name: event_code
            description: 사건 코드 `event_code`
"""


def write_yaml(root: Path, relative: str, body: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
    return path


def run_cli(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(arg) for arg in args)],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def run_manifest_cli(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MANIFEST_SCRIPT), *(str(arg) for arg in args)],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def run_catalog_compare_cli(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CATALOG_COMPARE_SCRIPT), *(str(arg) for arg in args)],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def run_cli_bytes(
    script: Path,
    *args: object,
    python_io_encoding: str,
    cwd: Path = REPO_ROOT,
) -> subprocess.CompletedProcess[bytes]:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = python_io_encoding
    environment.pop("PYTHONPATH", None)
    return subprocess.run(
        [sys.executable, str(script), *(str(arg) for arg in args)],
        cwd=cwd,
        env=environment,
        capture_output=True,
        check=False,
    )


def public_gold_metadata(
    *, visibility: str = "published_producer", contract_status: str = "dev_pending"
) -> dict[str, object]:
    metadata = {
        "anchor_universe": "서울시 자치구 기준 모집단입니다.",
        "column_order": list(BASE_COLUMN_ORDER),
        "contract_status": contract_status,
        "contract_version": "1.0",
        "documentation_language": "ko-KR",
        "do_not_use_for": "개별 시민의 행동을 판단하는 용도로 사용하지 않습니다.",
        "grain": "자치구와 기준 시각별 한 행입니다.",
        "joins": {},
        "lifecycle": {"status": "active"},
        "lineage": {
            "identifiers": {
                "as_of": {"columns": ["product_as_of_at"]},
                "publication": {"columns": ["published_at"]},
                "raw": {"columns": ["raw_object_key"]},
                "request": {"columns": ["request_id"]},
                "run": {"columns": ["dag_run_id"]},
            },
            "source_relations": ["source.weather.raw_public_metric"],
        },
        "maturity": "medium",
        "metrics": {
            "metric_value": {
                "additive_axes": ["admin_dong"],
                "aggregation": "sum",
                "denominator": "not_applicable",
                "expression": "sum(metric_value)",
                "non_additive_axes": ["time"],
                "null_meaning": "원천에서 지표를 제공하지 않은 상태입니다.",
                "unit": "건",
                "zero_meaning": "관측된 지표 건수가 없음을 뜻합니다.",
            }
        },
        "owner": "서울 데이터팀",
        "primary_key": ["district_id"],
        "product_question": "서울 자치구별 공개 지표는 무엇입니까?",
        "quality": {
            "completeness_explanation": "필수 원천 행의 수집 완전성을 설명합니다.",
            "coverage_explanation": "서울 자치구 기준 공간 범위를 설명합니다.",
            "freshness_explanation": "최신 원천 수집 시각과의 차이를 설명합니다.",
            "state_fields": {},
        },
        "row_meaning": "서울 자치구의 공개 지표 한 건을 나타냅니다.",
        "semantic_caveats": "수집 지연으로 최신 시점과 차이가 날 수 있습니다.",
        "space": {"enabled": False},
        "time": {
            "as_of_meaning": "제품이 반영한 최신 증거 시각을 뜻합니다.",
            "canonical_timezone": CANONICAL_TIMEZONE,
            "freshness_slo": "제품은 최신 증거를 15분 이내 반영하는 것을 목표로 합니다.",
            "late_repair_policy": "늦은 자료는 승인된 범위에서 재처리하고 결과를 다시 검증합니다.",
            "roles": {
                "product_as_of_at": {
                    "time_role": "as_of",
                    "timezone": CANONICAL_TIMEZONE,
                },
                "published_at": {
                    "time_role": "publication",
                    "timezone": CANONICAL_TIMEZONE,
                },
            },
        },
        "usage_guidance": "자치구 단위 비교와 추세 설명에 사용합니다.",
        "visibility": visibility,
    }
    if visibility == "published_producer":
        metadata.update(
            {
                "cross_domain_usage_examples": [
                    "교통 정책과 지역별 공개 지표를 함께 비교합니다.",
                    "문화 시설 분석에서 자치구 기준 보조 지표로 사용합니다.",
                ],
                "exposure_status": "none_no_live_consumer",
                "intended_consumer_types": ["analyst", "ai_catalog"],
            }
        )
    elif visibility == "served":
        metadata["exposure_status"] = "active_exposure"
    return metadata


def valid_manifest_node(
    unique_id: str,
    *,
    name: str | None = None,
    visibility: str = "published_producer",
    contract_status: str = "dev_pending",
) -> dict[str, object]:
    resolved_name = name or unique_id.rsplit(".", 1)[-1]
    return {
        "columns": {
            "district_id": {
                "config": {
                    "meta": {
                        "null_meaning": "기본 키이므로 null을 허용하지 않습니다.",
                        "nullable": False,
                        "semantic_role": "join_key",
                    }
                },
                "data_type": "string",
                "description": "서울 자치구를 구분하는 식별자입니다.",
                "name": "district_id",
            },
            "metric_value": {
                "config": {
                    "meta": {
                        "aggregation_behavior": "sum",
                        "null_meaning": "원천에서 지표를 제공하지 않은 상태입니다.",
                        "semantic_role": "metric",
                        "unit": "건",
                        "zero_meaning": "관측된 지표 건수가 없음을 뜻합니다.",
                    }
                },
                "data_type": "bigint",
                "description": "서울 자치구에서 관측한 공개 지표 값입니다.",
                "name": "metric_value",
            },
            "dag_run_id": {
                "config": {"meta": {"null_meaning": "실행 식별자가 없는 상태입니다.", "semantic_role": "lineage_id"}},
                "data_type": "string",
                "description": "원천 실행을 추적하는 DAG 실행 식별자입니다.",
                "name": "dag_run_id",
            },
            "product_as_of_at": {
                "config": {"meta": {"null_meaning": "제품 기준 시각을 계산할 수 없는 상태입니다.", "semantic_role": "timestamp", "time_role": "as_of", "timezone": CANONICAL_TIMEZONE}},
                "data_type": "timestamp(6)",
                "description": "제품이 반영한 최신 증거의 서울 기준 시각입니다.",
                "name": "product_as_of_at",
            },
            "published_at": {
                "config": {"meta": {"null_meaning": "게시 시각을 기록하지 못한 상태입니다.", "semantic_role": "timestamp", "time_role": "publication", "timezone": CANONICAL_TIMEZONE}},
                "data_type": "timestamp(6)",
                "description": "제품을 게시한 서울 기준 시각입니다.",
                "name": "published_at",
            },
            "raw_object_key": {
                "config": {"meta": {"null_meaning": "원본 객체를 연결할 수 없는 상태입니다.", "semantic_role": "lineage_id"}},
                "data_type": "string",
                "description": "원본 객체를 추적하는 안정 식별자입니다.",
                "name": "raw_object_key",
            },
            "request_id": {
                "config": {"meta": {"null_meaning": "요청 식별자가 없는 상태입니다.", "semantic_role": "lineage_id"}},
                "data_type": "string",
                "description": "원천 API 요청을 추적하는 식별자입니다.",
                "name": "request_id",
            },
        },
        "config": {
            "meta": {
                "public_gold": public_gold_metadata(
                    visibility=visibility, contract_status=contract_status
                )
            }
        },
        "depends_on": {"nodes": ["model.weather.silver_source", "source.weather.raw"]},
        "description": "서울 자치구별 공개 지표를 제공하는 골드 모델입니다.",
        "name": resolved_name,
        "resource_type": "model",
        "unique_id": unique_id,
    }


def valid_manifest_exposure(
    model_uid: str,
    *,
    name: str = "public_metric_application",
    maturity: str = "medium",
    owner: object = OWNER_MISSING,
) -> dict[str, object]:
    resolved_owner = (
        {"email": None, "name": "서울 서비스팀"}
        if owner is OWNER_MISSING
        else owner
    )
    return {
        "depends_on": {"nodes": [model_uid]},
        "maturity": maturity,
        "name": name,
        "owner": resolved_owner,
        "type": "application",
    }


def valid_reconciliation_test(
    model_uid: str,
    *,
    name: str = "reconcile_district_join",
    unique_id: str = "test.weather.unstable_hash_9f31",
) -> tuple[str, dict[str, object]]:
    return (
        unique_id,
        {
            "depends_on": {"nodes": [model_uid]},
            "name": name,
            "resource_type": "test",
            "unique_id": unique_id,
        },
    )


def valid_join_metadata() -> dict[str, object]:
    return {
        "cardinality": "many_to_one",
        "fan_out_policy": "대상 키가 중복되면 게시를 중단합니다.",
        "purpose": "서울 자치구 기준 정보를 연결합니다.",
        "reconciliation_test": "reconcile_district_join",
        "source_keys": ["district_id"],
        "target": "model.weather.dim_district",
    }


def enable_valid_space_contract(
    node: dict[str, object],
) -> list[tuple[str, dict[str, object]]]:
    for column_name in CANONICAL_SPACE_STAMP:
        node["columns"][column_name] = {
            "config": {
                "meta": {
                    "null_meaning": "정본 행정동 매핑이 없으면 null입니다.",
                    "semantic_role": "spatial_stamp",
                }
            },
            "data_type": "date" if column_name == "admin_dong_revision_date" else "string",
            "description": f"정본 공간축의 {column_name} 값을 설명하는 열입니다.",
            "name": column_name,
        }
    node["config"]["meta"]["public_gold"]["column_order"].extend(
        CANONICAL_SPACE_STAMP
    )
    node["depends_on"]["nodes"].append("model.asac_axes.dim_admin_dong")
    node["config"]["meta"]["public_gold"]["space"] = {
        "candidate_key_explanation": "원천 행정동 코드는 정본 매핑 전 후보 키로만 사용합니다.",
        "canonical_key": "admin_dong_code",
        "enabled": True,
        "fan_out_explanation": "정본 키가 중복되면 공간 게시를 중단합니다.",
        "mapping_version_explanation": "행정동 개정일과 매핑 버전을 함께 추적합니다.",
        "null_location_explanation": "매핑되지 않은 위치는 정본 stamp 전체를 null로 유지합니다.",
        "reconciliation_tests": [
            "reconcile_admin_dong_stamp",
            "reconcile_admin_dong_revision",
        ],
        "approved_revision_date": CANONICAL_SPACE_APPROVED_REVISION_DATE,
        "revision_field": "admin_dong_revision_date",
        "source_chain": list(CANONICAL_SPACE_SOURCE_CHAIN),
        "stamp_fields": list(CANONICAL_SPACE_STAMP),
    }
    return [
        valid_reconciliation_test(
            node["unique_id"],
            name="reconcile_admin_dong_stamp",
            unique_id="test.weather.space_stamp_hash",
        ),
        valid_reconciliation_test(
            node["unique_id"],
            name="reconcile_admin_dong_revision",
            unique_id="test.weather.space_revision_hash",
        ),
    ]


def valid_manifest(*nodes: tuple[str, dict[str, object]]) -> dict[str, object]:
    if not nodes:
        uid = "model.weather.gold_weather_public_metric"
        nodes = ((uid, valid_manifest_node(uid)),)
    manifest_nodes = dict(nodes)
    exposures: dict[str, object] = {}
    for uid, node in manifest_nodes.items():
        if node.get("resource_type") != "model":
            continue
        public_gold = node.get("config", {}).get("meta", {}).get("public_gold", {})
        if public_gold.get("visibility") == "served":
            exposure_uid = f"exposure.weather.{node.get('name', uid.rsplit('.', 1)[-1])}"
            exposures[exposure_uid] = valid_manifest_exposure(uid)
    return {
        "exposures": exposures,
        "metadata": {
            "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v12.json"
        },
        "nodes": manifest_nodes,
    }


def write_manifest(root: Path, manifest: object, *, name: str = "manifest.json") -> Path:
    path = root / name
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return path


def valid_catalog_pair() -> tuple[dict[str, object], dict[str, object]]:
    manifest = valid_manifest()
    invocation_id = "task-3a-fixture-invocation"
    manifest["metadata"]["invocation_id"] = invocation_id
    catalog_nodes: dict[str, object] = {}
    for uid, node in manifest["nodes"].items():
        public_gold = node.get("config", {}).get("meta", {}).get("public_gold", {})
        if public_gold.get("visibility") not in {"published_producer", "served"}:
            continue
        catalog_nodes[uid] = {
            "columns": {
                column_name: {
                    "comment": f"{column_name} 물리 카탈로그 주석",
                    "index": index,
                    "name": column_name,
                    "type": node["columns"][column_name]["data_type"],
                }
                for index, column_name in enumerate(
                    public_gold["column_order"], start=1
                )
            },
            "metadata": {
                "comment": "카탈로그 주석은 의미 증명이 아닙니다.",
                "name": node["name"],
                "type": "TABLE",
            },
            "unique_id": uid,
        }
    catalog = {
        "errors": [],
        "metadata": {
            "dbt_schema_version": "https://schemas.getdbt.com/dbt/catalog/v1.json",
            "generated_at": "2026-07-12T00:00:00Z",
            "invocation_id": invocation_id,
        },
        "nodes": catalog_nodes,
        "sources": {},
    }
    return manifest, catalog


def write_json_artifact(root: Path, name: str, value: object) -> Path:
    path = root / name
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return path


def write_escaped_json_artifact(root: Path, name: str, value: object) -> Path:
    path = root / name
    path.write_text(
        json.dumps(value, ensure_ascii=True, sort_keys=True), encoding="utf-8"
    )
    return path


def manifest_validator_module():
    return importlib.import_module("domains.weather.contracts.scripts.validate_public_gold_manifest")


def catalog_comparator_module():
    return importlib.import_module("domains.weather.contracts.scripts.compare_public_gold_catalog")


def errors_with_code(report: dict[str, object], code: str) -> list[dict[str, object]]:
    return [error for error in report["errors"] if error["code"] == code]


class ContractCliUtf8StdoutTests(unittest.TestCase):
    def test_all_contract_clis_emit_utf8_json_under_forced_stdio_encodings(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            valid_schema = write_yaml(root, "valid.yml", VALID_MIXED_SCHEMA)
            failing_schema = write_yaml(
                root,
                "failing.yml",
                """
                version: 2
                models:
                  - name: undocumented_model
                    description: English only
                """,
            )
            missing_schema = root / "없는-스키마-root"

            manifest, catalog = valid_catalog_pair()
            manifest_path = write_json_artifact(root, "manifest.json", manifest)
            catalog_path = write_json_artifact(root, "catalog.json", catalog)
            invalid_manifest_path = root / "invalid-manifest.json"
            invalid_manifest_path.write_text("{not json", encoding="utf-8")
            invalid_catalog_path = root / "invalid-catalog.json"
            invalid_catalog_path.write_text("{not json", encoding="utf-8")

            failing_catalog = copy.deepcopy(catalog)
            failing_catalog["nodes"]["model.weather.gold_weather_public_metric"][
                "columns"
            ].pop("request_id")
            failing_catalog_path = write_json_artifact(
                root, "failing-catalog.json", failing_catalog
            )

            cases = (
                (
                    "source_linter_pass",
                    SCRIPT,
                    ("--schema-root", valid_schema, "--require-language", "ko-KR"),
                    0,
                    "PASS",
                ),
                (
                    "source_linter_fail",
                    SCRIPT,
                    ("--schema-root", failing_schema, "--require-language", "ko-KR"),
                    1,
                    "FAIL",
                ),
                (
                    "source_linter_error",
                    SCRIPT,
                    ("--schema-root", missing_schema, "--require-language", "ko-KR"),
                    2,
                    "ERROR",
                ),
                (
                    "manifest_validator_pass",
                    MANIFEST_SCRIPT,
                    ("--manifest", manifest_path, "--require-language", "ko-KR"),
                    0,
                    "PASS",
                ),
                (
                    "manifest_validator_fail",
                    MANIFEST_SCRIPT,
                    (
                        "--manifest",
                        manifest_path,
                        "--resource",
                        "missing",
                        "--require-language",
                        "ko-KR",
                    ),
                    1,
                    "FAIL",
                ),
                (
                    "manifest_validator_error",
                    MANIFEST_SCRIPT,
                    (
                        "--manifest",
                        invalid_manifest_path,
                        "--require-language",
                        "ko-KR",
                    ),
                    2,
                    "ERROR",
                ),
                (
                    "catalog_comparator_pass",
                    CATALOG_COMPARE_SCRIPT,
                    (
                        "--manifest",
                        manifest_path,
                        "--catalog",
                        catalog_path,
                        "--require-language",
                        "ko-KR",
                    ),
                    0,
                    "PASS",
                ),
                (
                    "catalog_comparator_fail",
                    CATALOG_COMPARE_SCRIPT,
                    (
                        "--manifest",
                        manifest_path,
                        "--catalog",
                        failing_catalog_path,
                        "--require-language",
                        "ko-KR",
                    ),
                    1,
                    "FAIL",
                ),
                (
                    "catalog_comparator_error",
                    CATALOG_COMPARE_SCRIPT,
                    (
                        "--manifest",
                        manifest_path,
                        "--catalog",
                        invalid_catalog_path,
                        "--require-language",
                        "ko-KR",
                    ),
                    2,
                    "ERROR",
                ),
            )

            for python_io_encoding in ("ascii", "utf-16"):
                for name, script, arguments, expected_exit, expected_status in cases:
                    with self.subTest(
                        python_io_encoding=python_io_encoding,
                        name=name,
                    ):
                        result = run_cli_bytes(
                            script,
                            *arguments,
                            python_io_encoding=python_io_encoding,
                            cwd=root,
                        )
                        self.assertEqual(expected_exit, result.returncode, result.stderr)
                        self.assertEqual(b"", result.stderr)
                        rendered = result.stdout.decode("utf-8")
                        report = json.loads(rendered)
                        self.assertEqual(expected_status, report["status"])
                        self.assertTrue(rendered.endswith("\n"))
                        self.assertIn("이", rendered)
                        self.assertNotIn("\\u", rendered)
                        self.assertNotIn("Traceback", rendered)

    def test_utf8_stdout_helper_supports_string_io_fallback(self) -> None:
        artifact_io = importlib.import_module("domains.weather.contracts.scripts.artifact_io")
        stream = io.StringIO()

        artifact_io.write_utf8_stdout("한글 계약\n", stream=stream)

        self.assertEqual("한글 계약\n", stream.getvalue())


class SchemaContractSourceLinterTests(unittest.TestCase):
    def test_valid_mixed_schema_passes_with_complete_utf8_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            schema_path = write_yaml(root, "nested/schema.yml", VALID_MIXED_SCHEMA)

            report = lint.lint_schema_contracts([root], required_language="ko-KR")
            encoded = lint.render_report(report)

            self.assertEqual("PASS", report["status"])
            self.assertEqual([], report["errors"])
            self.assertEqual(
                {
                    "coverage_percentage": 100.0,
                    "description_fields_accounted": 9,
                    "description_fields_expected": 9,
                    "description_fields_present": 9,
                    "description_fields_unaccounted": 0,
                    "error_count": 0,
                    "files_scanned": 1,
                    "files_total": 1,
                    "resources_scanned": 5,
                    "resources_total": 5,
                    "resources_unaccounted": 0,
                },
                report["summary"],
            )
            self.assertEqual(schema_path.resolve().as_posix(), report["files"][0]["path"])
            self.assertEqual("PASS", report["files"][0]["scan_status"])
            self.assertEqual(
                [
                    ("model", "gold_weather_orders"),
                    ("model", "quoted_model"),
                    ("seed", "area_seed"),
                    ("source", "source:public_api"),
                    ("source_table", "source:public_api.events"),
                ],
                [(item["kind"], item["name"]) for item in report["resources"]],
            )
            self.assertIn("서울", encoded)
            self.assertNotIn("\\u", encoded)
            json.loads(encoded)

            descriptions = report["descriptions"]
            self.assertEqual(9, len(descriptions))
            self.assertTrue(all(item["accounted"] for item in descriptions))
            self.assertTrue(all(item["present"] for item in descriptions))
            self.assertTrue(all(item["language_status"] == "PASS" for item in descriptions))

    def test_cross_file_duplicates_use_nearest_project_scope_and_report_both_locations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first_project = root / "project-a"
            second_project = root / "project-b"
            write_yaml(first_project, "dbt_project.yml", "name: project_a\n")
            write_yaml(second_project, "dbt_project.yml", "name: project_b\n")
            first = write_yaml(
                first_project,
                "models/a.yml",
                """
                version: 2
                models:
                  - name: shared_model
                    description: 첫 번째 모델 설명
                seeds:
                  - name: shared_seed
                    description: 첫 번째 시드 설명
                sources:
                  - name: shared_source
                    description: 첫 번째 원천 설명
                    tables:
                      - name: shared_table
                        description: 첫 번째 원천 테이블 설명
                """,
            )
            second = write_yaml(
                first_project,
                "models/b.yml",
                """
                version: 2
                models:
                  - name: shared_model
                    description: 두 번째 모델 설명
                seeds:
                  - name: shared_seed
                    description: 두 번째 시드 설명
                sources:
                  - name: shared_source
                    description: 두 번째 원천 설명
                    tables:
                      - name: shared_table
                        description: 두 번째 원천 테이블 설명
                """,
            )
            write_yaml(
                second_project,
                "models/schema.yml",
                """
                version: 2
                models:
                  - name: shared_model
                    description: 다른 프로젝트의 모델 설명
                seeds:
                  - name: shared_seed
                    description: 다른 프로젝트의 시드 설명
                sources:
                  - name: shared_source
                    description: 다른 프로젝트의 원천 설명
                    tables:
                      - name: shared_table
                        description: 다른 프로젝트의 원천 테이블 설명
                """,
            )

            forward = lint.lint_schema_contracts(
                [second_project, first_project], required_language="ko-KR"
            )
            reverse = lint.lint_schema_contracts(
                [first_project, second_project], required_language="ko-KR"
            )

            self.assertEqual(lint.render_report(forward), lint.render_report(reverse))
            duplicates = errors_with_code(forward, "DUPLICATE_RESOURCE")
            self.assertEqual("FAIL", forward["status"])
            self.assertEqual("FAIL", forward["proof"]["source_yaml_uniqueness"])
            self.assertEqual(4, len(duplicates), duplicates)
            expected_names = {
                ("model", "shared_model"),
                ("seed", "shared_seed"),
                ("source", "source:shared_source"),
                ("source_table", "source:shared_source.shared_table"),
            }
            self.assertEqual(
                expected_names,
                {(error["resource_kind"], error["resource_name"]) for error in duplicates},
            )
            for error in duplicates:
                self.assertEqual([first.resolve().as_posix(), second.resolve().as_posix()], error["files"])
                self.assertEqual(2, len(error["lines"]))
                self.assertEqual(first_project.resolve().as_posix(), error["project_scope"])

            ambiguous = lint.lint_schema_contracts(
                [first_project, second_project],
                resources=["shared_model"],
                required_language="ko-KR",
            )
            self.assertEqual("FAIL", ambiguous["status"])
            selector_errors = errors_with_code(ambiguous, "RESOURCE_SELECTOR_AMBIGUOUS")
            self.assertEqual(1, len(selector_errors))
            self.assertEqual(
                [first_project.resolve().as_posix(), second_project.resolve().as_posix()],
                selector_errors[0]["project_scopes"],
            )

    def test_placeholders_must_be_the_whole_description_and_controlled_codes_are_prose(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = write_yaml(
                root,
                "semantic.yml",
                """
                version: 2
                models:
                  - name: todo_suffix
                    description: TODO입니다
                  - name: tbd_suffix
                    description: TBD임
                  - name: placeholder_suffix
                    description: placeholder 예정
                  - name: controlled_pending
                    description: "`PENDING` 상태의 의미를 설명합니다"
                  - name: controlled_unknown
                    description: 미정 상태는 null로 저장합니다
                """,
            )

            report = lint.lint_schema_contracts([path], required_language="ko-KR")

            placeholder_names = {
                error["resource_name"]
                for error in errors_with_code(report, "PLACEHOLDER_DESCRIPTION")
            }
            self.assertEqual({"todo_suffix", "tbd_suffix", "placeholder_suffix"}, placeholder_names)
            self.assertFalse(
                {"controlled_pending", "controlled_unknown"} & placeholder_names,
                report,
            )

    def test_placeholder_wrappers_and_deferred_variants_fail_but_real_sentences_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = write_yaml(
                root,
                "placeholder-wrappers.yml",
                """
                version: 2
                models:
                  - name: backtick_todo
                    description: "`TODO`입니다"
                  - name: backtick_tbd
                    description: "`TBD`임"
                  - name: curly_todo
                    description: “TODO”입니다
                  - name: bracket_unknown
                    description: 「미정」입니다
                  - name: combined_deferred
                    description: TODO - 추후 작성
                  - name: later_deferred
                    description: 나중에 작성
                  - name: actual_todo_semantics
                    description: "`TODO`는 원천 시스템의 정상 상태 코드입니다"
                  - name: actual_later_sentence
                    description: 나중에 수집된 값은 ingest_at으로 구분합니다
                """,
            )

            report = lint.lint_schema_contracts([path], required_language="ko-KR")

            placeholders = {
                error["resource_name"]
                for error in errors_with_code(report, "PLACEHOLDER_DESCRIPTION")
            }
            self.assertEqual(
                {
                    "backtick_todo",
                    "backtick_tbd",
                    "curly_todo",
                    "bracket_unknown",
                    "combined_deferred",
                    "later_deferred",
                },
                placeholders,
            )
            self.assertFalse(
                {"actual_todo_semantics", "actual_later_sentence"} & placeholders,
                report,
            )

    def test_placeholder_allowlist_grammar_handles_wrappers_and_compounds_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = write_yaml(
                root,
                "placeholder-grammar.yml",
                """
                version: 2
                models:
                  - name: ascii_paren
                    description: (TODO)입니다
                  - name: fullwidth_paren
                    description: （TODO）입니다
                  - name: square_wrapper
                    description: 【미정】입니다
                  - name: markdown_bold
                    description: "**TODO**입니다"
                  - name: markdown_underline
                    description: "__TBD__임"
                  - name: slash_compound
                    description: TODO / 추후 작성
                  - name: colon_compound
                    description: "TODO : 추후 작성"
                  - name: dash_compound
                    description: TODO-추후 작성
                  - name: later_scheduled
                    description: 나중에 작성 예정
                  - name: enum_prose
                    description: "`TODO`는 원천 시스템의 정상 상태 코드입니다"
                  - name: later_prose
                    description: 나중에 수집된 값은 ingest_at으로 구분합니다
                  - name: punctuation_prose
                    description: TODO 상태는 원천 코드이며 미정 값은 null입니다
                """,
            )
            report = lint.lint_schema_contracts([path], required_language="ko-KR")
            placeholders = {
                error["resource_name"]
                for error in errors_with_code(report, "PLACEHOLDER_DESCRIPTION")
            }
            self.assertEqual(
                {
                    "ascii_paren", "fullwidth_paren", "square_wrapper",
                    "markdown_bold", "markdown_underline", "slash_compound",
                    "colon_compound", "dash_compound", "later_scheduled",
                },
                placeholders,
            )
            self.assertFalse(
                {"enum_prose", "later_prose", "punctuation_prose"} & placeholders,
                report,
            )

    def test_wrapped_placeholders_allow_only_terminal_punctuation_after_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = write_yaml(
                root,
                "placeholder-terminal.yml",
                """
                version: 2
                models:
                  - name: backtick_period
                    description: "`TODO`입니다."
                  - name: paren_bang
                    description: (TODO)입니다!
                  - name: bracket_stop
                    description: 【미정】입니다。
                  - name: markdown_question
                    description: "**TODO**입니다?"
                  - name: prose_period
                    description: "`TODO`는 원천 상태 코드입니다."
                  - name: prose_bang
                    description: 미정 상태는 null로 저장합니다!
                """,
            )
            report = lint.lint_schema_contracts([path], required_language="ko-KR")
            placeholders = {
                error["resource_name"]
                for error in errors_with_code(report, "PLACEHOLDER_DESCRIPTION")
            }
            self.assertEqual(
                {"backtick_period", "paren_bang", "bracket_stop", "markdown_question"},
                placeholders,
            )
            self.assertFalse({"prose_period", "prose_bang"} & placeholders, report)

    def test_unaccounted_structure_reduces_coverage_but_missing_description_is_accounted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            missing_description = write_yaml(
                root,
                "missing-description.yml",
                """
                version: 2
                models:
                  - name: documented_later
                """,
            )
            missing_report = lint.lint_schema_contracts(
                [missing_description], required_language="ko-KR"
            )
            self.assertEqual(100.0, missing_report["summary"]["coverage_percentage"])
            self.assertEqual(0, missing_report["summary"]["description_fields_unaccounted"])

            nameless_column = write_yaml(
                root,
                "nameless-column.yml",
                """
                version: 2
                models:
                  - name: model_with_nameless_column
                    description: 이름 없는 열을 검증하는 모델
                    columns:
                      - description: 이름을 분류할 수 없는 열 설명
                """,
            )
            column_report = lint.lint_schema_contracts(
                [nameless_column], required_language="ko-KR"
            )
            self.assertEqual(1, column_report["summary"]["description_fields_unaccounted"])
            self.assertLess(column_report["summary"]["coverage_percentage"], 100.0)
            self.assertEqual("FAIL", column_report["proof"]["source_yaml_uniqueness"])

            missing_selector = lint.lint_schema_contracts(
                [missing_description],
                resources=["not_declared"],
                required_language="ko-KR",
            )
            self.assertEqual(1, missing_selector["summary"]["resources_unaccounted"])
            self.assertEqual(1, missing_selector["summary"]["description_fields_unaccounted"])
            self.assertLess(missing_selector["summary"]["coverage_percentage"], 100.0)

            nameless_resource = write_yaml(
                root,
                "nameless-resource.yml",
                """
                version: 2
                models:
                  - description: 이름을 분류할 수 없는 모델 설명
                """,
            )
            resource_report = lint.lint_schema_contracts(
                [nameless_resource], required_language="ko-KR"
            )
            self.assertEqual(1, resource_report["summary"]["resources_unaccounted"])
            self.assertEqual(1, resource_report["summary"]["description_fields_unaccounted"])
            self.assertLess(resource_report["summary"]["coverage_percentage"], 100.0)
            self.assertEqual("FAIL", resource_report["proof"]["source_yaml_uniqueness"])

    def test_every_report_has_machine_readable_source_declaration_proof_boundaries(self) -> None:
        expected_limit = (
            "이 도구는 실제 relation 컬럼·타입·순서, SQL projection, grain, 최신 선택과 "
            "tie-break, reconciliation 또는 데이터 의미 정합성을 증명하지 않습니다."
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            valid = write_yaml(root, "valid.yml", VALID_MIXED_SCHEMA)
            invalid = write_yaml(
                root,
                "invalid.yml",
                """
                version: 2
                models:
                  - name: invalid_model
                    description: English only
                """,
            )
            reports = [
                (lint.lint_schema_contracts([valid], required_language="ko-KR"), "PASS", "PASS"),
                (lint.lint_schema_contracts([invalid], required_language="ko-KR"), "FAIL", "PASS"),
                (
                    lint.lint_schema_contracts([root / "missing"], required_language="ko-KR"),
                    "FAIL",
                    "FAIL",
                ),
            ]
            for report, declared, uniqueness in reports:
                with self.subTest(status=report["status"]):
                    self.assertEqual("source_yaml_declaration", report["proof_scope"])
                    self.assertEqual(expected_limit, report["claim_limitations_ko"])
                    self.assertEqual(
                        {
                            "data_contract": "NOT_RUN",
                            "declared_contract": declared,
                            "manual_semantic_review": "REQUIRED",
                            "physical_contract": "NOT_RUN",
                            "source_yaml_uniqueness": uniqueness,
                        },
                        report["proof"],
                    )

    def test_duplicate_column_and_resource_report_both_source_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = write_yaml(
                root,
                "duplicates.yml",
                """
                version: 2
                models:
                  - name: repeated_model
                    description: 반복 모델 설명
                    columns:
                      - name: dup_col
                        description: 첫 번째 열 설명
                      - name: dup_col
                        description: 두 번째 열 설명
                  - name: repeated_model
                    description: 두 번째 모델 설명
                """,
            )

            report = lint.lint_schema_contracts([path], required_language="ko-KR")

            self.assertEqual("FAIL", report["status"])
            duplicate_column = errors_with_code(report, "DUPLICATE_COLUMN")
            duplicate_resource = errors_with_code(report, "DUPLICATE_RESOURCE")
            self.assertEqual(1, len(duplicate_column))
            self.assertEqual(
                {
                    "code": "DUPLICATE_COLUMN",
                    "column": "dup_col",
                    "file": path.resolve().as_posix(),
                    "lines": [6, 8],
                    "message": "duplicate column 'dup_col' in model 'repeated_model'",
                    "resource_kind": "model",
                    "resource_name": "repeated_model",
                },
                duplicate_column[0],
            )
            self.assertEqual(1, len(duplicate_resource))
            self.assertEqual([3, 10], duplicate_resource[0]["lines"])
            self.assertEqual("model", duplicate_resource[0]["resource_kind"])
            self.assertEqual("repeated_model", duplicate_resource[0]["resource_name"])

    def test_description_failures_identify_exact_entity_and_field(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_yaml(
                root,
                "semantic.yml",
                """
                version: 2
                models:
                  - name: missing_model
                    columns:
                      - name: missing_column
                  - name: english_model
                    description: Human readable English description
                    columns:
                      - name: placeholder_col
                        description: TODO
                      - name: identifier_only
                        description: "`identifier_only`"
                      - name: korean_placeholder
                        description: 추후 작성
                """,
            )

            report = lint.lint_schema_contracts([root], required_language="ko-KR")

            self.assertEqual("FAIL", report["status"])
            self.assertEqual(100.0, report["summary"]["coverage_percentage"])
            keyed = {
                (error["code"], error["entity_kind"], error["resource_name"], error.get("column"))
                for error in report["errors"]
                if "entity_kind" in error
            }
            self.assertEqual(
                {
                    ("MISSING_DESCRIPTION", "resource", "missing_model", None),
                    ("MISSING_DESCRIPTION", "column", "missing_model", "missing_column"),
                    ("DESCRIPTION_LANGUAGE", "resource", "english_model", None),
                    ("PLACEHOLDER_DESCRIPTION", "column", "english_model", "placeholder_col"),
                    ("IDENTIFIER_ONLY_DESCRIPTION", "column", "english_model", "identifier_only"),
                    ("PLACEHOLDER_DESCRIPTION", "column", "english_model", "korean_placeholder"),
                },
                keyed,
            )
            for error in report["errors"]:
                if "entity_kind" in error:
                    self.assertEqual("description", error["field"])

    def test_unsupported_constructs_fail_the_whole_file_without_pass_coverage(self) -> None:
        cases = {
            "anchor": "description: &shared 서울 설명",
            "alias": "description: *shared",
            "merge_key": "<<: *defaults",
            "tab": "\tdescription: 서울 설명",
            "nested_flow": "values: [['x']]",
            "multiline_flow": "values: [\n          'x'\n        ]",
            "unbalanced_flow": "values: ['x'",
            "malformed_indentation": "   columns:\n      - name: bad\n        description: 잘못된 들여쓰기",
            "unclassified_line": "this line has no mapping separator",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for name, construct in cases.items():
                with self.subTest(name=name):
                    path = write_yaml(
                        root,
                        f"{name}.yml",
                        f"""
                        version: 2
                        models:
                          - name: model_{name}
                            description: 정상 모델 설명
                            columns:
                              - name: value
                                description: 정상 열 설명
                                {construct}
                        """,
                    )
                    report = lint.lint_schema_contracts([path], required_language="ko-KR")
                    self.assertEqual("FAIL", report["status"])
                    self.assertEqual("FAIL", report["files"][0]["scan_status"])
                    self.assertEqual(0, report["summary"]["files_scanned"])
                    self.assertLess(report["summary"]["coverage_percentage"], 100.0)
                    self.assertTrue(
                        any(error["code"] == "UNSUPPORTED_YAML" for error in report["errors"]),
                        report,
                    )

    def test_resource_selection_limits_semantics_but_not_lexical_safety(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            safe_path = write_yaml(
                root,
                "safe.yml",
                """
                version: 2
                models:
                  - name: selected_model
                    description: 선택 모델 설명
                    columns:
                      - name: selected_id
                        description: 선택 식별자 설명
                  - name: ignored_model
                    description: English only and ignored semantically
                    columns:
                      - name: ignored_id
                """,
            )

            report = lint.lint_schema_contracts(
                [safe_path], resources=["selected_model"], required_language="ko-KR"
            )

            self.assertEqual("PASS", report["status"])
            self.assertEqual(["selected_model"], [item["name"] for item in report["resources"]])
            self.assertEqual(2, report["summary"]["description_fields_expected"])
            self.assertEqual(100.0, report["summary"]["coverage_percentage"])

            unsafe_path = write_yaml(
                root,
                "unsafe.yml",
                """
                version: 2
                models:
                  - name: selected_model
                    description: 선택 모델 설명
                  - name: ignored_model
                    description: &unsafe English ignored semantically
                """,
            )
            unsafe_report = lint.lint_schema_contracts(
                [unsafe_path], resources=["selected_model"], required_language="ko-KR"
            )
            self.assertEqual("FAIL", unsafe_report["status"])
            unsafe_file = next(item for item in unsafe_report["files"] if item["path"] == unsafe_path.resolve().as_posix())
            self.assertEqual("FAIL", unsafe_file["scan_status"])
            self.assertLess(unsafe_report["summary"]["coverage_percentage"], 100.0)

    def test_plain_description_braces_are_not_misclassified_as_flow_collections(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = write_yaml(
                root,
                "plain-braces.yml",
                """
                version: 2
                models:
                  - name: endpoint_model
                    description: KOPIS 상세 경로 /{mt10id} 원천 모델
                    meta:
                      database: "{{ target.database }}"
                      values: ['x', 'y']
                      freshness: {count: 30, period: hour}
                    columns:
                      - name: endpoint_id
                        description: 상세 경로 식별자
                """,
            )

            report = lint.lint_schema_contracts([path], required_language="ko-KR")

            self.assertEqual("PASS", report["status"])
            self.assertEqual(100.0, report["summary"]["coverage_percentage"])

    def test_root_and_creation_order_do_not_change_json_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first = root / "first"
            second = root / "second"
            write_yaml(second, "z.yaml", VALID_MIXED_SCHEMA.replace("gold_weather_orders", "gold_weather_orders_z"))
            write_yaml(first, "a.yml", VALID_MIXED_SCHEMA.replace("gold_weather_orders", "gold_weather_orders_a"))

            forward = lint.render_report(
                lint.lint_schema_contracts([first, second], required_language="ko-KR")
            )
            reverse = lint.render_report(
                lint.lint_schema_contracts([second, first], required_language="ko-KR")
            )

            self.assertEqual(forward.encode("utf-8"), reverse.encode("utf-8"))
            paths = [item["path"] for item in json.loads(forward)["files"]]
            self.assertEqual(sorted(paths), paths)

    def test_cli_exit_codes_stdout_output_file_and_invalid_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            valid = write_yaml(root, "valid.yml", VALID_MIXED_SCHEMA)
            invalid = write_yaml(
                root,
                "invalid.yml",
                """
                version: 2
                models:
                  - name: english_model
                    description: English only
                """,
            )

            passed = run_cli("--schema-root", valid, "--require-language", "ko-KR")
            self.assertEqual(0, passed.returncode, passed.stderr)
            self.assertEqual("", passed.stderr)
            self.assertEqual("PASS", json.loads(passed.stdout)["status"])
            self.assertIn("서울", passed.stdout)
            self.assertNotIn("\\u", passed.stdout)

            output_path = root / "report.json"
            to_file = run_cli(
                "--schema-root",
                valid,
                "--require-language",
                "ko-KR",
                "--output",
                output_path,
            )
            self.assertEqual(0, to_file.returncode, to_file.stderr)
            self.assertEqual("", to_file.stdout)
            self.assertEqual("PASS", json.loads(output_path.read_text(encoding="utf-8"))["status"])

            failed = run_cli("--schema-root", invalid, "--require-language", "ko-KR")
            self.assertEqual(1, failed.returncode)
            self.assertEqual("FAIL", json.loads(failed.stdout)["status"])

            missing = run_cli("--schema-root", root / "does-not-exist", "--require-language", "ko-KR")
            self.assertEqual(2, missing.returncode)
            self.assertEqual("ERROR", json.loads(missing.stdout)["status"])
            self.assertEqual("INVALID_ROOT", json.loads(missing.stdout)["errors"][0]["code"])

            bad_output = run_cli(
                "--schema-root",
                valid,
                "--require-language",
                "ko-KR",
                "--output",
                root / "missing-parent" / "report.json",
            )
            self.assertEqual(2, bad_output.returncode)
            self.assertEqual("", bad_output.stdout)
            self.assertIn("cannot write output", bad_output.stderr)

    def test_yaml_node_properties_are_rejected_only_outside_quotes(self) -> None:
        unsupported = {
            "tag": "description: !custom 한국어 설명",
            "wide_anchor": "description: &shared.name 한국어 설명",
            "wide_alias": "description: *shared/path",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for name, construct in unsupported.items():
                with self.subTest(name=name):
                    path = write_yaml(
                        root,
                        f"{name}.yml",
                        f"""
                        version: 2
                        models:
                          - name: model_{name}
                            description: 정상 모델 설명
                            columns:
                              - name: value
                                {construct}
                        """,
                    )

                    report = lint.lint_schema_contracts([path], required_language="ko-KR")

                    self.assertEqual("FAIL", report["status"])
                    self.assertEqual("FAIL", report["files"][0]["scan_status"])
                    self.assertEqual(
                        ["UNSUPPORTED_YAML"],
                        [error["code"] for error in report["errors"]],
                    )

            quoted_path = write_yaml(
                root,
                "quoted-node-like-literals.yml",
                """
                version: 2
                models:
                  - name: quoted_node_literals
                    description: "서울 &source.name *literal/path !custom 문자 설명"
                    columns:
                      - name: literal_text
                        description: '서울 &single.anchor *single/alias !single 문자 설명'
                """,
            )
            quoted_report = lint.lint_schema_contracts(
                [quoted_path], required_language="ko-KR"
            )

            self.assertEqual("PASS", quoted_report["status"])
            self.assertEqual([], quoted_report["errors"])

    def test_invalid_plain_scalar_indicators_mapping_separators_and_controls_fail_closed(self) -> None:
        cases = {
            "at_indicator": "description: @later",
            "backtick_indicator": "description: `later`",
            "percent_indicator": "description: %later",
            "bad_literal_indicator": "description: |invalid",
            "bad_folded_indicator": "description: >invalid",
            "question_indicator": "description: ? later",
            "dash_indicator": "description: - later",
            "colon_indicator": "description: : later",
            "comma_indicator": "description: ,later",
            "nul_control": "description: 서울\x00설명",
            "c0_control": "description: 서울\x01설명",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for name, construct in cases.items():
                with self.subTest(name=name):
                    path = write_yaml(
                        root,
                        f"{name}.yml",
                        (
                            "version: 2\n"
                            "models:\n"
                            f"  - name: model_{name}\n"
                            "    description: 정상 모델 설명\n"
                            "    columns:\n"
                            "      - name: value\n"
                            f"        {construct}\n"
                        ),
                    )
                    report = lint.lint_schema_contracts([path], required_language="ko-KR")
                    self.assertEqual("FAIL", report["status"], report)
                    self.assertEqual("FAIL", report["files"][0]["scan_status"])
                    self.assertEqual(["UNSUPPORTED_YAML"], [error["code"] for error in report["errors"]])

            no_space_fixtures = {
                "name": "version: 2\nmodels:\n  - name:model\n    description: 모델 설명\n",
                "description": "version: 2\nmodels:\n  - name: model\n    description:한국어 설명\n",
            }
            for name, body in no_space_fixtures.items():
                with self.subTest(no_space=name):
                    path = write_yaml(root, f"no-space-{name}.yml", body)
                    report = lint.lint_schema_contracts([path], required_language="ko-KR")
                    self.assertEqual("FAIL", report["status"], report)
                    self.assertEqual("FAIL", report["files"][0]["scan_status"])

    def test_yaml_double_quoted_x_n_and_json_escapes_decode_and_unknown_escape_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            valid = write_yaml(
                root,
                "yaml-escapes.yml",
                """
                version: 2
                models:
                  - name: escaped_model
                    description: "서울\\x20설명\\N다음 줄"
                    columns:
                      - name: escaped_column
                        description: "탭\\t설명과 유니코드 \\uC11C"
                """,
            )
            report = lint.lint_schema_contracts([valid], required_language="ko-KR")
            self.assertEqual("PASS", report["status"], report)
            values = [item["value"] for item in report["descriptions"]]
            self.assertIn("서울 설명\u0085다음 줄", values)
            self.assertIn("탭\t설명과 유니코드 서", values)

            invalid = write_yaml(
                root,
                "unknown-escape.yml",
                """
                version: 2
                models:
                  - name: unknown_escape
                    description: "서울\\q설명"
                """,
            )
            invalid_report = lint.lint_schema_contracts([invalid], required_language="ko-KR")
            self.assertEqual("FAIL", invalid_report["status"])
            self.assertEqual("FAIL", invalid_report["files"][0]["scan_status"])

    def test_yaml_double_quote_decoder_preserves_parity_and_validates_codepoints(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            valid_body = (
                "version: 2\nmodels:\n"
                "  - name: single_x\n" + r'    description: "서울\x20설명"' + "\n"
                "  - name: single_n\n" + r'    description: "서울\N설명"' + "\n"
                "  - name: double_x\n" + r'    description: "서울\\x20설명"' + "\n"
                "  - name: double_n\n" + r'    description: "서울\\N설명"' + "\n"
                "  - name: yaml_safe\n" + r'    description: "공백\_구분\L줄\P문단 \U0001F600\ 설명"' + "\n"
                "  - name: json_safe\n" + r'    description: "따옴표 \"서울\" 탭\t 개행\n 복귀\r 유니코드\uC11C 슬래시\/"' + "\n"
            )
            valid = write_yaml(root, "parity.yml", valid_body)
            report = lint.lint_schema_contracts([valid], required_language="ko-KR")
            self.assertEqual("PASS", report["status"], report)
            values = {item["resource_name"]: item["value"] for item in report["descriptions"]}
            self.assertEqual("서울 설명", values["single_x"])
            self.assertEqual("서울\u0085설명", values["single_n"])
            self.assertEqual(r"서울\x20설명", values["double_x"])
            self.assertEqual(r"서울\N설명", values["double_n"])
            self.assertEqual("공백\u00a0구분\u2028줄\u2029문단 😀 설명", values["yaml_safe"])
            self.assertEqual('따옴표 "서울" 탭\t 개행\n 복귀\r 유니코드서 슬래시/', values["json_safe"])

            invalid_escapes = {
                "unknown": r"\q",
                "short_x": r"\x2",
                "short_u": r"\u123",
                "out_of_range": r"\U00110000",
                "surrogate": r"\uD800",
                "forbidden_control": r"\x00",
                "backspace_control": r"\b",
                "formfeed_control": r"\f",
            }
            for name, escape in invalid_escapes.items():
                with self.subTest(name=name):
                    path = write_yaml(
                        root,
                        f"invalid-{name}.yml",
                        "version: 2\nmodels:\n"
                        f"  - name: invalid_{name}\n"
                        f'    description: "서울{escape}설명"\n',
                    )
                    invalid_report = lint.lint_schema_contracts([path], required_language="ko-KR")
                    self.assertEqual("FAIL", invalid_report["status"], invalid_report)
                    self.assertEqual("FAIL", invalid_report["files"][0]["scan_status"])

    def test_extra_plain_scalar_mapping_separator_fails_but_common_colons_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            invalid_values = {
                "colon_space": "description: 서울: 설명",
                "colon_end": "description: 서울:",
                "name_extra": "name: model: extra",
            }
            for name, line in invalid_values.items():
                with self.subTest(name=name):
                    body = (
                        "version: 2\nmodels:\n"
                        f"  - {line if name == 'name_extra' else 'name: model_' + name}\n"
                    )
                    if name == "name_extra":
                        body += "    description: 정상 모델 설명\n"
                    else:
                        body += f"    {line}\n"
                    path = write_yaml(root, f"invalid-{name}.yml", body)
                    report = lint.lint_schema_contracts([path], required_language="ko-KR")
                    self.assertEqual("FAIL", report["status"], report)
                    self.assertEqual("FAIL", report["files"][0]["scan_status"])

            valid = write_yaml(
                root,
                "valid-colons.yml",
                """
                version: 2
                models:
                  - name: valid_colons
                    description: 서울 링크 https://example.com/data 시간 12:30 경로 /{mt10id}
                """,
            )
            valid_report = lint.lint_schema_contracts([valid], required_language="ko-KR")
            self.assertEqual("PASS", valid_report["status"], valid_report)

    def test_plain_scalar_mid_quotes_and_brackets_do_not_hide_mapping_separators(self) -> None:
        invalid_values = {
            "double_quote": '서울 "foo: bar" 설명',
            "single_quote": "서울 'foo: bar' 설명",
            "square": "서울 [foo: bar] 설명",
            "curly": "서울 {foo: bar} 설명",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for name, value in invalid_values.items():
                with self.subTest(name=name):
                    path = write_yaml(
                        root,
                        f"invalid-{name}.yml",
                        "version: 2\nmodels:\n"
                        f"  - name: invalid_{name}\n"
                        f"    description: {value}\n",
                    )
                    report = lint.lint_schema_contracts([path], required_language="ko-KR")
                    self.assertEqual("FAIL", report["status"], report)
                    self.assertEqual("FAIL", report["files"][0]["scan_status"])

            valid = write_yaml(
                root,
                "valid-embedded.yml",
                """
                version: 2
                models:
                  - name: valid_embedded
                    description: 서울 https://example.com 12:30 /{mt10id} "foo" [bar] {baz} 설명
                """,
            )
            valid_report = lint.lint_schema_contracts([valid], required_language="ko-KR")
            self.assertEqual("PASS", valid_report["status"], valid_report)

    def test_raw_c1_controls_fail_except_yaml_printable_nel(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for codepoint in (0x80, 0x86, 0x9F):
                with self.subTest(codepoint=hex(codepoint)):
                    path = write_yaml(
                        root,
                        f"c1-{codepoint:02x}.yml",
                        "version: 2\nmodels:\n"
                        f"  - name: c1_{codepoint:02x}\n"
                        f"    description: 서울{chr(codepoint)}설명\n",
                    )
                    report = lint.lint_schema_contracts([path], required_language="ko-KR")
                    self.assertEqual("FAIL", report["status"], report)
                    self.assertEqual("FAIL", report["files"][0]["scan_status"])

            nel = write_yaml(
                root,
                "nel.yml",
                "version: 2\nmodels:\n"
                "  - name: raw_nel\n"
                "    description: 서울\u0085설명\n"
                "  - name: escaped_nel\n"
                + r'    description: "서울\N설명"' + "\n",
            )
            report = lint.lint_schema_contracts([nel], required_language="ko-KR")
            self.assertEqual("PASS", report["status"], report)
            values = {item["resource_name"]: item["value"] for item in report["descriptions"]}
            self.assertEqual("서울\u0085설명", values["raw_nel"])
            self.assertEqual("서울\u0085설명", values["escaped_nel"])

    def test_implicit_nested_flow_reserved_closers_and_bad_block_indent_fail_closed(self) -> None:
        unsupported = {
            "implicit_flow_map": "values: [key: value]",
            "implicit_flow_sequence": "values: [- nested]",
            "implicit_flow_map_value": "freshness: {count: nested: value}",
            "implicit_flow_sequence_value": "freshness: {count: - nested}",
            "leading_square_closer": "description: ] 한국어 설명",
            "leading_curly_closer": "description: } 한국어 설명",
            "explicit_block_indent": "description: |4-\n  너무 얕은 블록 설명",
            "implicit_block_dedent": (
                "description: |\n"
                "    첫 번째 블록 설명\n"
                "  뒤에서 낮아진 블록 설명"
            ),
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for name, construct in unsupported.items():
                with self.subTest(name=name):
                    path = write_yaml(
                        root,
                        f"{name}.yml",
                        (
                            "version: 2\n"
                            "models:\n"
                            f"  - name: model_{name}\n"
                            "    description: 정상 모델 설명\n"
                            "    columns:\n"
                            "      - name: value\n"
                            "        description: 정상 열 설명\n"
                            f"{textwrap.indent(construct, '        ')}\n"
                        ),
                    )

                    report = lint.lint_schema_contracts([path], required_language="ko-KR")

                    self.assertEqual("FAIL", report["status"], report)
                    self.assertEqual("FAIL", report["files"][0]["scan_status"])
                    self.assertTrue(
                        any(error["code"] == "UNSUPPORTED_YAML" for error in report["errors"]),
                        report,
                    )

    def test_schema_root_and_discovered_symlinks_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            outside = base / "outside"
            approved = base / "approved"
            outside.mkdir()
            approved.mkdir()
            outside_yaml = write_yaml(outside, "outside.yml", VALID_MIXED_SCHEMA)

            root_link = base / "root-link"
            root_link.symlink_to(outside, target_is_directory=True)
            file_link = approved / "escape.yml"
            file_link.symlink_to(outside_yaml)
            directory_link = approved / "linked-directory"
            directory_link.symlink_to(outside, target_is_directory=True)

            for path in (root_link, file_link, directory_link):
                with self.subTest(path=path.name):
                    schema_root = path if path != directory_link else approved
                    report = lint.lint_schema_contracts(
                        [schema_root], required_language="ko-KR"
                    )

                    self.assertEqual("ERROR", report["status"])
                    self.assertTrue(
                        any(error["code"] == "PATH_UNSAFE" for error in report["errors"]),
                        report,
                    )
                    self.assertNotIn("루트 외부", lint.render_report(report))

    def test_parser_input_bounds_return_deterministic_json_instead_of_tracebacks(self) -> None:
        def nested_mapping(depth: int) -> str:
            lines = ["root:"]
            for index in range(max(depth - 1, 0)):
                lines.append(f"{'  ' * (index + 1)}level_{index}:")
            lines.append(f"{'  ' * depth}leaf: value")
            return "\n".join(lines) + "\n"

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            within_depth = write_yaml(
                root,
                "within-depth.yml",
                nested_mapping(lint.MAX_NESTING_DEPTH),
            )
            within_report = lint.lint_schema_contracts(
                [within_depth], required_language="ko-KR"
            )
            self.assertEqual("PASS", within_report["status"], within_report)

            over_limit_fixtures = {
                "file_size": "x" * (lint.MAX_FILE_BYTES + 1),
                "line_count": "# line\n" * (lint.MAX_LINE_COUNT + 1),
                "line_length": "description: " + "가" * lint.MAX_LINE_LENGTH + "\n",
                "scalar_length": (
                    "description: |\n"
                    + "  "
                    + ("가" * 1000 + "\n  ")
                    * (lint.MAX_SCALAR_LENGTH // 1000 + 1)
                ),
                "nesting_depth": nested_mapping(lint.MAX_NESTING_DEPTH + 1),
            }
            rendered_reports: dict[str, bytes] = {}
            for name, body in over_limit_fixtures.items():
                with self.subTest(name=name):
                    path = write_yaml(root, f"{name}.yml", body)
                    report = lint.lint_schema_contracts([path], required_language="ko-KR")
                    rendered = lint.render_report(report).encode("utf-8")

                    self.assertEqual("FAIL", report["status"], report)
                    self.assertEqual("FAIL", report["files"][0]["scan_status"])
                    self.assertEqual(
                        ["INPUT_LIMIT_EXCEEDED"],
                        [error["code"] for error in report["errors"]],
                    )
                    self.assertNotIn(b"Traceback", rendered)
                    rendered_reports[name] = rendered

                    repeated = lint.render_report(
                        lint.lint_schema_contracts([path], required_language="ko-KR")
                    ).encode("utf-8")
                    self.assertEqual(rendered, repeated)

            self.assertEqual(set(over_limit_fixtures), set(rendered_reports))

    def test_output_rejects_input_collision_and_symlink_without_modifying_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            schema_path = write_yaml(root, "schema.yml", VALID_MIXED_SCHEMA)
            original_schema = schema_path.read_bytes()

            collision = run_cli(
                "--schema-root",
                schema_path,
                "--require-language",
                "ko-KR",
                "--output",
                schema_path,
            )
            self.assertEqual(2, collision.returncode)
            self.assertEqual("", collision.stdout)
            self.assertIn("cannot write output", collision.stderr)
            self.assertEqual(original_schema, schema_path.read_bytes())

            target = root / "existing-target.json"
            target.write_text("do-not-overwrite", encoding="utf-8")
            output_link = root / "report-link.json"
            output_link.symlink_to(target)
            linked = run_cli(
                "--schema-root",
                schema_path,
                "--require-language",
                "ko-KR",
                "--output",
                output_link,
            )
            self.assertEqual(2, linked.returncode)
            self.assertEqual("", linked.stdout)
            self.assertIn("cannot write output", linked.stderr)
            self.assertEqual("do-not-overwrite", target.read_text(encoding="utf-8"))

            safe_output = root / "safe-report.json"
            successful = run_cli(
                "--schema-root",
                schema_path,
                "--require-language",
                "ko-KR",
                "--output",
                safe_output,
            )
            self.assertEqual(0, successful.returncode, successful.stderr)
            self.assertEqual("PASS", json.loads(safe_output.read_text(encoding="utf-8"))["status"])
            self.assertEqual([], list(root.glob(f".{safe_output.name}.*.tmp")))

    def test_output_collision_preflight_uses_raw_roots_before_early_error_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)

            unsupported = write_yaml(root, "unsupported-language.yml", VALID_MIXED_SCHEMA)
            unsupported_bytes = unsupported.read_bytes()
            unsupported_result = run_cli(
                "--schema-root", unsupported,
                "--require-language", "en-US",
                "--output", unsupported,
            )
            self.assertEqual(2, unsupported_result.returncode)
            self.assertEqual("", unsupported_result.stdout)
            self.assertIn("collides", unsupported_result.stderr)
            self.assertEqual(unsupported_bytes, unsupported.read_bytes())

            partial = write_yaml(root, "partial-root.yml", VALID_MIXED_SCHEMA)
            partial_bytes = partial.read_bytes()
            partial_result = run_cli(
                "--schema-root", partial,
                "--schema-root", root / "missing-root",
                "--require-language", "ko-KR",
                "--output", partial,
            )
            self.assertEqual(2, partial_result.returncode)
            self.assertIn("collides", partial_result.stderr)
            self.assertEqual(partial_bytes, partial.read_bytes())

            target = write_yaml(root, "symlink-target.yml", VALID_MIXED_SCHEMA)
            target_bytes = target.read_bytes()
            schema_link = root / "schema-link.yml"
            schema_link.symlink_to(target)
            symlink_result = run_cli(
                "--schema-root", schema_link,
                "--require-language", "ko-KR",
                "--output", target,
            )
            self.assertEqual(2, symlink_result.returncode)
            self.assertIn("collides", symlink_result.stderr)
            self.assertEqual(target_bytes, target.read_bytes())

    def test_every_raw_root_path_is_collision_protected_before_suffix_or_existence_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)

            for name in ("valuable.txt", "valuable"):
                with self.subTest(existing=name):
                    path = root / name
                    original = b"ORIGINAL-DO-NOT-OVERWRITE\n"
                    path.write_bytes(original)
                    result = run_cli(
                        "--schema-root", path,
                        "--require-language", "ko-KR",
                        "--output", path,
                    )
                    self.assertEqual(2, result.returncode)
                    self.assertIn("collides", result.stderr)
                    self.assertEqual(original, path.read_bytes())

            missing = root / "missing-root"
            missing_result = run_cli(
                "--schema-root", missing,
                "--require-language", "ko-KR",
                "--output", missing,
            )
            self.assertEqual(2, missing_result.returncode)
            self.assertIn("collides", missing_result.stderr)
            self.assertFalse(missing.exists())

            partial = root / "partial-input.txt"
            partial_bytes = b"PARTIAL-ROOT-BYTES\n"
            partial.write_bytes(partial_bytes)
            valid = write_yaml(root, "valid-partial.yml", VALID_MIXED_SCHEMA)
            partial_result = run_cli(
                "--schema-root", valid,
                "--schema-root", partial,
                "--require-language", "ko-KR",
                "--output", partial,
            )
            self.assertEqual(2, partial_result.returncode)
            self.assertIn("collides", partial_result.stderr)
            self.assertEqual(partial_bytes, partial.read_bytes())

            target = root / "alias-target.txt"
            target_bytes = b"ALIAS-TARGET-BYTES\n"
            target.write_bytes(target_bytes)
            alias = root / "alias-root"
            alias.symlink_to(target)
            alias_result = run_cli(
                "--schema-root", alias,
                "--require-language", "ko-KR",
                "--output", target,
            )
            self.assertEqual(2, alias_result.returncode)
            self.assertIn("collides", alias_result.stderr)
            self.assertEqual(target_bytes, target.read_bytes())

    def test_canonicalized_output_parent_symlink_is_allowed_but_leaf_symlink_remains_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            schema_path = write_yaml(root, "schema.yml", VALID_MIXED_SCHEMA)
            real_parent = root / "real-output"
            real_parent.mkdir()
            linked_parent = root / "linked-output"
            linked_parent.symlink_to(real_parent, target_is_directory=True)
            output = linked_parent / "report.json"

            result = run_cli(
                "--schema-root", schema_path,
                "--require-language", "ko-KR",
                "--output", output,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("PASS", json.loads(output.read_text(encoding="utf-8"))["status"])

            leaf_target = real_parent / "leaf-target.json"
            leaf_target.write_text("keep", encoding="utf-8")
            leaf_link = linked_parent / "leaf-link.json"
            leaf_link.symlink_to(leaf_target)
            blocked = run_cli(
                "--schema-root", schema_path,
                "--require-language", "ko-KR",
                "--output", leaf_link,
            )
            self.assertEqual(2, blocked.returncode)
            self.assertIn("output symlinks are unsupported", blocked.stderr)
            self.assertEqual("keep", leaf_target.read_text(encoding="utf-8"))

    def test_output_inside_raw_directory_is_blocked_lexically_and_canonically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            root = base / "input-root"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            write_yaml(root, "schema.yml", VALID_MIXED_SCHEMA)
            valuable = write_yaml(outside, "valuable.yml", "ORIGINAL: BYTES\n")
            original = valuable.read_bytes()
            linked_directory = root / "linked-dir"
            linked_directory.symlink_to(outside, target_is_directory=True)
            destructive_output = linked_directory / "valuable.yml"

            blocked = run_cli(
                "--schema-root", root,
                "--require-language", "ko-KR",
                "--output", destructive_output,
            )
            self.assertEqual(2, blocked.returncode)
            self.assertIn("inside a schema root", blocked.stderr)
            self.assertEqual(original, valuable.read_bytes())

            clean_root = base / "clean-root"
            write_yaml(clean_root, "schema.yml", VALID_MIXED_SCHEMA)
            allowed_output = outside / "report.json"
            allowed = run_cli(
                "--schema-root", clean_root,
                "--require-language", "ko-KR",
                "--output", allowed_output,
            )
            self.assertEqual(0, allowed.returncode, allowed.stderr)
            self.assertEqual("PASS", json.loads(allowed_output.read_text(encoding="utf-8"))["status"])

    def test_descendant_symlink_targets_are_protected_regardless_of_suffix_or_existence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            root = base / "input-root"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            write_yaml(root, "schema.yml", VALID_MIXED_SCHEMA)

            cases = (
                ("linked-file.txt", "valuable.txt"),
                ("non-yaml-link.txt", "valuable.yml"),
            )
            for link_name, target_name in cases:
                with self.subTest(link=link_name, target=target_name):
                    target = outside / target_name
                    original = f"ORIGINAL-{target_name}\n".encode("utf-8")
                    target.write_bytes(original)
                    link = root / link_name
                    link.symlink_to(target)
                    result = run_cli(
                        "--schema-root", root,
                        "--require-language", "ko-KR",
                        "--output", target,
                    )
                    self.assertEqual(2, result.returncode)
                    self.assertIn("collides", result.stderr)
                    self.assertEqual(original, target.read_bytes())

            broken_target = outside / "future-target.txt"
            broken_link = root / "broken-link.txt"
            broken_link.symlink_to(broken_target)
            broken_result = run_cli(
                "--schema-root", root,
                "--require-language", "ko-KR",
                "--output", broken_target,
            )
            self.assertEqual(2, broken_result.returncode)
            self.assertIn("collides", broken_result.stderr)
            self.assertFalse(broken_target.exists())


class PublicGoldManifestValidatorTests(unittest.TestCase):
    def test_complete_korean_manifest_passes_and_exports_readable_proof_bounded_catalog(self) -> None:
        self.assertTrue(MANIFEST_SCRIPT.is_file(), "manifest validator script is missing")
        validator = manifest_validator_module()
        manifest = valid_manifest()
        manifest["future_additive_field"] = {"accepted": True}
        node = manifest["nodes"]["model.weather.gold_weather_public_metric"]
        node["config"]["meta"]["public_gold"]["future_additive_contract_field"] = "허용"

        report, catalog = validator.validate_manifest(manifest, required_language="ko-KR")

        self.assertEqual("PASS", report["status"])
        self.assertEqual([], report["errors"])
        self.assertIsNotNone(catalog)
        self.assertEqual(
            {
                "data_contract": "NOT_RUN",
                "declared_contract": "PASS",
                "manual_semantic_review": "REQUIRED",
                "physical_contract": "NOT_RUN",
                "source_yaml_uniqueness": "NOT_RUN",
            },
            report["proof"],
        )
        self.assertEqual(report["proof"], catalog["proof"])
        self.assertIn("실제 컬럼", report["claim_limitations_ko"])
        self.assertEqual("public-gold-ai-contract/v1", catalog["catalog_schema_version"])
        self.assertEqual(
            ["model.weather.gold_weather_public_metric"],
            [resource["unique_id"] for resource in catalog["resources"]],
        )
        rendered = validator.render_json(catalog)
        self.assertTrue(rendered.endswith("\n"))
        self.assertIn("서울", rendered)
        self.assertNotIn("\\u", rendered)
        self.assertNotIn("generated_at", rendered)
        self.assertNotIn("credentials", rendered)
        self.assertNotIn("future_additive_contract_field", rendered)

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manifest_path = write_manifest(root, manifest)
            catalog_path = root / "catalog.json"
            result = run_manifest_cli(
                "--manifest", manifest_path,
                "--require-language", "ko-KR",
                "--output", catalog_path,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("PASS", json.loads(result.stdout)["status"])
            self.assertEqual("", result.stderr)
            self.assertEqual(rendered, catalog_path.read_text(encoding="utf-8"))

    def test_required_model_language_and_prose_fail_at_exact_paths(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        cases = (
            (
                "missing_product_question",
                lambda node: node["config"]["meta"]["public_gold"].pop("product_question"),
                f"nodes.{uid}.config.meta.public_gold.product_question",
            ),
            (
                "wrong_language",
                lambda node: node["config"]["meta"]["public_gold"].__setitem__(
                    "documentation_language", "en-US"
                ),
                f"nodes.{uid}.config.meta.public_gold.documentation_language",
            ),
            (
                "english_model",
                lambda node: node.__setitem__("description", "English only description"),
                f"nodes.{uid}.description",
            ),
            (
                "placeholder_column",
                lambda node: node["columns"]["metric_value"].__setitem__(
                    "description", "TODO"
                ),
                f"nodes.{uid}.columns.metric_value.description",
            ),
            (
                "identifier_only_column",
                lambda node: node["columns"]["metric_value"].__setitem__(
                    "description", "metric_value"
                ),
                f"nodes.{uid}.columns.metric_value.description",
            ),
        )
        for name, mutate, expected_path in cases:
            with self.subTest(name=name):
                node = valid_manifest_node(uid)
                mutate(node)
                report, catalog = validator.validate_manifest(valid_manifest((uid, node)))
                self.assertEqual("FAIL", report["status"], report)
                self.assertIsNone(catalog)
                self.assertIn(expected_path, [error["path"] for error in report["errors"]])
                self.assertEqual("FAIL", report["proof"]["declared_contract"])

    def test_column_contract_and_metric_fields_fail_at_exact_paths(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        base = f"nodes.{uid}.columns.metric_value"
        cases = (
            ("description", lambda column: column.pop("description"), f"{base}.description"),
            ("data_type", lambda column: column.pop("data_type"), f"{base}.data_type"),
            ("meta", lambda column: column["config"].pop("meta"), f"{base}.config.meta"),
            ("unit", lambda column: column["config"]["meta"].pop("unit"), f"{base}.config.meta.unit"),
            (
                "zero_meaning",
                lambda column: column["config"]["meta"].pop("zero_meaning"),
                f"{base}.config.meta.zero_meaning",
            ),
            (
                "null_meaning",
                lambda column: column["config"]["meta"].pop("null_meaning"),
                f"{base}.config.meta.null_meaning",
            ),
            (
                "aggregation_behavior",
                lambda column: column["config"]["meta"].pop("aggregation_behavior"),
                f"{base}.config.meta.aggregation_behavior",
            ),
        )
        for name, mutate, expected_path in cases:
            with self.subTest(name=name):
                node = valid_manifest_node(uid)
                mutate(node["columns"]["metric_value"])
                report, _ = validator.validate_manifest(valid_manifest((uid, node)))
                self.assertEqual("FAIL", report["status"], report)
                self.assertIn(expected_path, [error["path"] for error in report["errors"]])

        for name, value, expected_path in (
            ("unsafe_role", "label", f"nodes.{uid}.columns.district_id.config.meta.semantic_role"),
            ("nullable_key", True, f"nodes.{uid}.columns.district_id.config.meta.nullable"),
        ):
            with self.subTest(name=name):
                node = valid_manifest_node(uid)
                key_meta = node["columns"]["district_id"]["config"]["meta"]
                key_meta["semantic_role" if name == "unsafe_role" else "nullable"] = value
                report, _ = validator.validate_manifest(valid_manifest((uid, node)))
                self.assertIn(expected_path, [error["path"] for error in report["errors"]])

    def test_dev_pending_allows_missing_enforcement_but_enforced_status_requires_it(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        pending = valid_manifest_node(uid, contract_status="dev_pending")
        pending_report, _ = validator.validate_manifest(valid_manifest((uid, pending)))
        self.assertEqual("PASS", pending_report["status"], pending_report)

        enforced = valid_manifest_node(uid, contract_status="enforced")
        enforced_report, catalog = validator.validate_manifest(valid_manifest((uid, enforced)))
        self.assertEqual("FAIL", enforced_report["status"])
        self.assertIsNone(catalog)
        self.assertIn(
            f"nodes.{uid}.config.contract.enforced",
            [error["path"] for error in enforced_report["errors"]],
        )

        enforced["config"]["contract"] = {"enforced": True}
        passed_report, passed_catalog = validator.validate_manifest(valid_manifest((uid, enforced)))
        self.assertEqual("PASS", passed_report["status"], passed_report)
        self.assertEqual("enforced", passed_catalog["resources"][0]["contract_status"])

        legacy_fallback = valid_manifest_node(uid, contract_status="enforced")
        legacy_fallback["config"]["contract"] = {}
        legacy_fallback["contract"] = {"enforced": True}
        fallback_report, _ = validator.validate_manifest(valid_manifest((uid, legacy_fallback)))
        self.assertEqual("PASS", fallback_report["status"], fallback_report)

    def test_canonical_and_legacy_metadata_fallbacks_pass_but_conflicts_fail(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"

        fallback = valid_manifest_node(uid)
        fallback["meta"] = fallback["config"].pop("meta")
        column = fallback["columns"]["district_id"]
        column["meta"] = column["config"].pop("meta")
        fallback_report, _ = validator.validate_manifest(valid_manifest((uid, fallback)))
        self.assertEqual("PASS", fallback_report["status"], fallback_report)

        compatible = valid_manifest_node(uid)
        compatible["meta"] = copy.deepcopy(compatible["config"]["meta"])
        compatible_column = compatible["columns"]["district_id"]
        compatible_column["meta"] = copy.deepcopy(compatible_column["config"]["meta"])
        compatible_report, _ = validator.validate_manifest(valid_manifest((uid, compatible)))
        self.assertEqual("PASS", compatible_report["status"], compatible_report)

        node_conflict = copy.deepcopy(compatible)
        node_conflict["meta"]["public_gold"]["product_question"] = "서로 다른 질문입니다."
        conflict_report, _ = validator.validate_manifest(valid_manifest((uid, node_conflict)))
        self.assertIn(
            f"nodes.{uid}.config.meta.public_gold",
            [error["path"] for error in conflict_report["errors"]],
        )

        column_conflict = copy.deepcopy(compatible)
        column_conflict["columns"]["district_id"]["meta"]["semantic_role"] = "label"
        conflict_report, _ = validator.validate_manifest(valid_manifest((uid, column_conflict)))
        self.assertIn(
            f"nodes.{uid}.columns.district_id.config.meta.semantic_role",
            [error["path"] for error in conflict_report["errors"]],
        )

    def test_all_visibilities_are_validated_but_only_public_producers_are_exported(self) -> None:
        validator = manifest_validator_module()
        nodes = []
        for visibility in ("internal", "candidate", "published_producer", "served"):
            uid = f"model.weather.gold_{visibility}"
            nodes.append((uid, valid_manifest_node(uid, visibility=visibility)))
        report, catalog = validator.validate_manifest(valid_manifest(*nodes))
        self.assertEqual("PASS", report["status"], report)
        self.assertEqual(
            ["model.weather.gold_published_producer", "model.weather.gold_served"],
            [resource["unique_id"] for resource in catalog["resources"]],
        )

        nodes[0][1]["description"] = "English invalid internal model"
        invalid_report, invalid_catalog = validator.validate_manifest(valid_manifest(*nodes))
        self.assertEqual("FAIL", invalid_report["status"])
        self.assertIsNone(invalid_catalog)

    def test_manifest_order_does_not_change_catalog_bytes(self) -> None:
        validator = manifest_validator_module()
        first_uid = "model.weather.gold_a"
        second_uid = "model.weather.gold_b"
        first_node = valid_manifest_node(first_uid, visibility="served")
        second_node = valid_manifest_node(second_uid)
        forward = valid_manifest((first_uid, first_node), (second_uid, second_node))
        reverse = copy.deepcopy(forward)
        reverse["nodes"] = dict(reversed(list(reverse["nodes"].items())))
        for node in reverse["nodes"].values():
            node["columns"] = dict(reversed(list(node["columns"].items())))
            node["depends_on"]["nodes"] = list(reversed(node["depends_on"]["nodes"]))

        forward_report, forward_catalog = validator.validate_manifest(forward)
        reverse_report, reverse_catalog = validator.validate_manifest(reverse)
        self.assertEqual("PASS", forward_report["status"])
        self.assertEqual("PASS", reverse_report["status"])
        forward_bytes = validator.render_json(forward_catalog).encode("utf-8")
        reverse_bytes = validator.render_json(reverse_catalog).encode("utf-8")
        self.assertEqual(forward_bytes, reverse_bytes)
        self.assertEqual(
            BASE_COLUMN_ORDER,
            forward_catalog["resources"][0]["public_gold"].get("column_order"),
        )
        self.assertEqual(
            BASE_COLUMN_ORDER,
            reverse_catalog["resources"][0]["public_gold"].get("column_order"),
        )
        self.assertIn("서울".encode(), forward_bytes)
        self.assertNotIn(b"\\u", forward_bytes)

    def test_column_order_is_required_distinct_and_matches_declared_columns_exactly(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        base_path = f"nodes.{uid}.config.meta.public_gold.column_order"

        def missing(value: dict[str, object]) -> None:
            value.pop("column_order")

        def invalid_type(value: dict[str, object]) -> None:
            value["column_order"] = {"district_id": 1}

        def blank_item(value: dict[str, object]) -> None:
            value["column_order"].append(" ")

        def duplicate_item(value: dict[str, object]) -> None:
            value["column_order"].append("district_id")

        def missing_column(value: dict[str, object]) -> None:
            value["column_order"].remove("request_id")

        def extra_column(value: dict[str, object]) -> None:
            value["column_order"].append("not_declared")

        cases = (
            ("missing", missing, base_path),
            ("invalid_type", invalid_type, base_path),
            ("blank_item", blank_item, f"{base_path}[7]"),
            ("duplicate", duplicate_item, f"{base_path}[7]"),
            ("missing_column", missing_column, base_path),
            ("extra_column", extra_column, f"{base_path}[7]"),
        )
        for name, mutate, expected_path in cases:
            with self.subTest(name=name):
                node = valid_manifest_node(uid)
                mutate(node["config"]["meta"]["public_gold"])
                report, catalog = validator.validate_manifest(valid_manifest((uid, node)))
                self.assertEqual("FAIL", report["status"], report)
                self.assertIsNone(catalog)
                self.assertIn(expected_path, [error["path"] for error in report["errors"]])

    def test_column_order_controls_exported_columns_without_mapping_order_inference(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        node = valid_manifest_node(uid)
        declared_order = list(reversed(BASE_COLUMN_ORDER))
        node["config"]["meta"]["public_gold"]["column_order"] = declared_order
        node["columns"] = dict(
            reversed(list(node["columns"].items()))
        )

        report, catalog = validator.validate_manifest(valid_manifest((uid, node)))

        self.assertEqual("PASS", report["status"], report)
        self.assertEqual(
            declared_order,
            [column["name"] for column in catalog["resources"][0]["columns"]],
        )
        self.assertEqual(
            declared_order,
            catalog["resources"][0]["public_gold"]["column_order"],
        )

    def test_selectors_resolve_uniquely_and_missing_or_ambiguous_are_contract_failures(self) -> None:
        validator = manifest_validator_module()
        first_uid = "model.weather.package_a"
        second_uid = "model.other.package_b"
        first = valid_manifest_node(first_uid, name="shared")
        second = valid_manifest_node(second_uid, name="shared")
        manifest = valid_manifest((first_uid, first), (second_uid, second))

        selected_report, selected_catalog = validator.validate_manifest(
            manifest, resources=[first_uid]
        )
        self.assertEqual("PASS", selected_report["status"])
        self.assertEqual([first_uid], [item["unique_id"] for item in selected_catalog["resources"]])

        for selector, code in (("missing", "RESOURCE_NOT_FOUND"), ("shared", "RESOURCE_AMBIGUOUS")):
            with self.subTest(selector=selector):
                report, catalog = validator.validate_manifest(manifest, resources=[selector])
                self.assertEqual("FAIL", report["status"], report)
                self.assertIsNone(catalog)
                self.assertIn(code, [error["code"] for error in report["errors"]])

    def test_artifact_shape_and_cli_io_errors_use_exit_two_without_partial_catalog(self) -> None:
        validator = manifest_validator_module()
        for name, manifest in (
            ("wrong_v12", {**valid_manifest(), "metadata": {"dbt_schema_version": "v11"}}),
            ("nodes_list", {**valid_manifest(), "nodes": []}),
            ("exposures_list", {**valid_manifest(), "exposures": []}),
        ):
            with self.subTest(name=name):
                report, catalog = validator.validate_manifest(manifest)
                self.assertEqual("ERROR", report["status"], report)
                self.assertIsNone(catalog)
                self.assertEqual("FAIL", report["proof"]["declared_contract"])

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            invalid_json = root / "invalid.json"
            invalid_json.write_text("{not json", encoding="utf-8")
            invalid_result = run_manifest_cli(
                "--manifest", invalid_json, "--require-language", "ko-KR"
            )
            self.assertEqual(2, invalid_result.returncode, invalid_result.stderr)
            self.assertEqual("ERROR", json.loads(invalid_result.stdout)["status"])

            manifest_path = write_manifest(root, valid_manifest())
            missing_result = run_manifest_cli(
                "--manifest", manifest_path,
                "--resource", "missing",
                "--require-language", "ko-KR",
            )
            self.assertEqual(1, missing_result.returncode, missing_result.stderr)
            self.assertEqual("FAIL", json.loads(missing_result.stdout)["status"])

            bad_output = root / "missing-parent" / "catalog.json"
            output_result = run_manifest_cli(
                "--manifest", manifest_path,
                "--require-language", "ko-KR",
                "--output", bad_output,
            )
            self.assertEqual(2, output_result.returncode)
            self.assertEqual("ERROR", json.loads(output_result.stdout)["status"])
            self.assertFalse(bad_output.exists())

    def test_recursive_export_boundary_rejects_forbidden_keys_and_absolute_paths(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        base = f"nodes.{uid}.config.meta.public_gold.quality"
        cases = (
            ("generated_at", {"checks": [{"generated_at": "2026-07-12T00:00:00Z"}]}, f"{base}.checks[0].generated_at"),
            ("credentials", {"checks": [{"credentials": "value"}]}, f"{base}.checks[0].credentials"),
            ("token", {"auth": [{"token": "value"}]}, f"{base}.auth[0].token"),
            ("secret", {"auth": [{"secret": "value"}]}, f"{base}.auth[0].secret"),
            ("access_key", {"auth": [{"access_key": "value"}]}, f"{base}.auth[0].access_key"),
            ("environment_schema", {"targets": [{"environment_schema": "dev_user"}]}, f"{base}.targets[0].environment_schema"),
            ("absolute_path_key", {"files": [{"absolute_path": "relative.json"}]}, f"{base}.files[0].absolute_path"),
            ("absolute_path_value", {"files": [{"reference": "/private/tmp/contract.json"}]}, f"{base}.files[0].reference"),
        )
        for name, unsafe_quality, expected_path in cases:
            with self.subTest(name=name):
                node = valid_manifest_node(uid)
                node["config"]["meta"]["public_gold"]["quality"] = unsafe_quality
                report, catalog = validator.validate_manifest(valid_manifest((uid, node)))
                self.assertEqual("FAIL", report["status"], report)
                self.assertIsNone(catalog)
                self.assertIn(expected_path, [error["path"] for error in report["errors"]])

        safe = valid_manifest((uid, valid_manifest_node(uid)))
        safe["future_additive_manifest_field"] = {
            "generated_at": "manifest additive fields are not exported"
        }
        safe_report, safe_catalog = validator.validate_manifest(safe)
        self.assertEqual("PASS", safe_report["status"], safe_report)
        self.assertNotIn("future_additive_manifest_field", validator.render_json(safe_catalog))

    def test_conflict_equality_distinguishes_json_booleans_from_numbers_deeply(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"

        node = valid_manifest_node(uid)
        node["config"]["meta"]["public_gold"]["quality"]["future_rules"] = [
            {"enabled": True}
        ]
        node["meta"] = copy.deepcopy(node["config"]["meta"])
        node["meta"]["public_gold"]["quality"]["future_rules"][0]["enabled"] = 1
        report, _ = validator.validate_manifest(valid_manifest((uid, node)))
        self.assertIn("CONFLICTING_METADATA", [error["code"] for error in report["errors"]])

        column_node = valid_manifest_node(uid)
        column = column_node["columns"]["district_id"]
        column["config"]["meta"]["details"] = [{"enabled": True}]
        column["meta"] = copy.deepcopy(column["config"]["meta"])
        column["meta"]["details"][0]["enabled"] = 1
        report, _ = validator.validate_manifest(valid_manifest((uid, column_node)))
        self.assertIn(
            f"nodes.{uid}.columns.district_id.config.meta.details",
            [error["path"] for error in report["errors"]],
        )

        numeric_node = valid_manifest_node(uid)
        numeric_node["config"]["meta"]["public_gold"]["quality"]["future_threshold"] = 1
        numeric_node["meta"] = copy.deepcopy(numeric_node["config"]["meta"])
        numeric_node["meta"]["public_gold"]["quality"]["future_threshold"] = 1.0
        numeric_report, _ = validator.validate_manifest(valid_manifest((uid, numeric_node)))
        self.assertEqual("PASS", numeric_report["status"], numeric_report)

    def test_fallback_validation_errors_retain_actual_metadata_and_contract_paths(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"

        legacy_column_node = valid_manifest_node(uid)
        legacy_metric = legacy_column_node["columns"]["metric_value"]
        legacy_metric["meta"] = legacy_metric["config"].pop("meta")
        legacy_metric["meta"].pop("unit")
        legacy_report, _ = validator.validate_manifest(valid_manifest((uid, legacy_column_node)))
        self.assertIn(
            f"nodes.{uid}.columns.metric_value.meta.unit",
            [error["path"] for error in legacy_report["errors"]],
        )

        canonical_column_node = valid_manifest_node(uid)
        canonical_column_node["columns"]["metric_value"]["config"]["meta"].pop("unit")
        canonical_report, _ = validator.validate_manifest(
            valid_manifest((uid, canonical_column_node))
        )
        self.assertIn(
            f"nodes.{uid}.columns.metric_value.config.meta.unit",
            [error["path"] for error in canonical_report["errors"]],
        )

        legacy_contract_node = valid_manifest_node(uid, contract_status="enforced")
        legacy_contract_node["contract"] = {"enforced": False}
        contract_report, _ = validator.validate_manifest(
            valid_manifest((uid, legacy_contract_node))
        )
        self.assertIn(
            f"nodes.{uid}.contract.enforced",
            [error["path"] for error in contract_report["errors"]],
        )

    def test_output_error_preserves_successful_declared_contract_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manifest_path = write_manifest(root, valid_manifest())
            result = run_manifest_cli(
                "--manifest", manifest_path,
                "--require-language", "ko-KR",
                "--output", root / "missing-parent" / "catalog.json",
            )
            self.assertEqual(2, result.returncode)
            report = json.loads(result.stdout)
            self.assertEqual("ERROR", report["status"])
            self.assertEqual("PASS", report["proof"]["declared_contract"])

            invalid = root / "invalid.json"
            invalid.write_text("{invalid", encoding="utf-8")
            invalid_result = run_manifest_cli(
                "--manifest", invalid, "--require-language", "ko-KR"
            )
            self.assertEqual(2, invalid_result.returncode)
            self.assertEqual(
                "FAIL", json.loads(invalid_result.stdout)["proof"]["declared_contract"]
            )

    def test_output_rejects_existing_hard_link_identity_without_mutating_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manifest_path = write_manifest(root, valid_manifest())
            original = manifest_path.read_bytes()
            hard_link = root / "catalog-hard-link.json"
            os.link(manifest_path, hard_link)

            result = run_manifest_cli(
                "--manifest", manifest_path,
                "--require-language", "ko-KR",
                "--output", hard_link,
            )

            self.assertEqual(2, result.returncode, result.stdout)
            self.assertEqual(original, manifest_path.read_bytes())
            self.assertEqual(original, hard_link.read_bytes())
            self.assertEqual("PASS", json.loads(result.stdout)["proof"]["declared_contract"])

    def test_json_preflight_rejects_nonfinite_depth_and_container_limits_without_output_mutation(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"

        nonfinite = valid_manifest((uid, valid_manifest_node(uid)))
        nonfinite["nodes"][uid]["config"]["meta"]["public_gold"]["quality"] = {
            "threshold": float("nan")
        }
        report, catalog = validator.validate_manifest(nonfinite)
        self.assertEqual("ERROR", report["status"], report)
        self.assertIsNone(catalog)
        self.assertIn(
            f"nodes.{uid}.config.meta.public_gold.quality.threshold",
            [error["path"] for error in report["errors"]],
        )
        with self.assertRaises(ValueError):
            validator.render_json({"not_finite": float("inf")})

        too_deep = valid_manifest()
        cursor: dict[str, object] = {}
        too_deep["future_deep"] = cursor
        for index in range(70):
            child: dict[str, object] = {}
            cursor[f"level_{index}"] = child
            cursor = child
        depth_report, _ = validator.validate_manifest(too_deep)
        self.assertEqual("ERROR", depth_report["status"], depth_report)
        self.assertIn("JSON_LIMIT_EXCEEDED", [error["code"] for error in depth_report["errors"]])

        production_sized = valid_manifest()
        production_sized["future_many"] = [{} for _ in range(11_500)]
        production_sized_report, _ = validator.validate_manifest(production_sized)
        self.assertEqual("PASS", production_sized_report["status"], production_sized_report)

        too_many = valid_manifest()
        too_many["future_many"] = [
            {} for _ in range(validator.MAX_JSON_CONTAINERS + 100)
        ]
        count_report, _ = validator.validate_manifest(too_many)
        self.assertEqual("ERROR", count_report["status"], count_report)
        self.assertIn("JSON_LIMIT_EXCEEDED", [error["code"] for error in count_report["errors"]])

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            output = root / "catalog.json"
            output.write_text("KEEP", encoding="utf-8")
            for constant in ("NaN", "Infinity", "-Infinity"):
                with self.subTest(constant=constant):
                    manifest_path = root / f"manifest-{constant.replace('-', 'minus')}.json"
                    body = json.dumps(valid_manifest(), ensure_ascii=False)
                    body = body[:-1] + f', "future_nonfinite": {constant}' + "}"
                    manifest_path.write_text(body, encoding="utf-8")
                    result = run_manifest_cli(
                        "--manifest", manifest_path,
                        "--require-language", "ko-KR",
                        "--output", output,
                    )
                    self.assertEqual(2, result.returncode, result.stdout)
                    self.assertEqual("ERROR", json.loads(result.stdout)["status"])
                    self.assertEqual("KEEP", output.read_text(encoding="utf-8"))

    def test_manifest_json_preflight_rejects_lone_surrogate_values_and_keys(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            cases = []
            value_manifest = valid_manifest()
            value_manifest["future_surrogate"] = "\ud800"
            cases.append(("value", value_manifest))
            key_manifest = valid_manifest()
            key_manifest["future_mapping"] = {"\ud800": True}
            cases.append(("key", key_manifest))
            for name, manifest in cases:
                with self.subTest(name=name):
                    manifest_path = write_escaped_json_artifact(
                        root, f"manifest-surrogate-{name}.json", manifest
                    )
                    self.assertIn("\\ud800", manifest_path.read_text(encoding="utf-8"))
                    output = root / f"catalog-surrogate-{name}.json"
                    output.write_text("KEEP", encoding="utf-8")

                    result = run_manifest_cli(
                        "--manifest", manifest_path,
                        "--require-language", "ko-KR",
                        "--output", output,
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

    def test_catalog_omits_structured_metadata_not_yet_validated_by_task_2b1(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        node = valid_manifest_node(uid)
        public_gold = node["config"]["meta"]["public_gold"]
        public_gold["quality"]["future_unvalidated"] = {
            "updated_at": "2026-07-12T12:34:56Z",
            "target_schema": "dev_user",
            "auth_value": "opaque-but-not-validated",
        }
        public_gold["lineage"]["future_unvalidated"] = {
            "timestamp": "2026-07-12T12:34:56+09:00"
        }

        report, catalog = validator.validate_manifest(valid_manifest((uid, node)))

        self.assertEqual("PASS", report["status"], report)
        rendered = validator.render_json(catalog)
        for forbidden_literal in (
            "future_unvalidated",
            "updated_at",
            "target_schema",
            "auth_value",
            "2026-07-12T12:34:56Z",
            "2026-07-12T12:34:56+09:00",
        ):
            self.assertNotIn(forbidden_literal, rendered)
        exported_public_gold = catalog["resources"][0]["public_gold"]
        self.assertFalse(
            {"future_unvalidated", "updated_at", "target_schema", "auth_value", "timestamp"}
            & exported_public_gold.keys()
        )

    def test_node_legacy_public_gold_fallback_requires_config_meta_key_to_be_absent(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        node = valid_manifest_node(uid)
        legacy_meta = node["config"]["meta"]
        node["config"]["meta"] = {"unrelated": "canonical metadata exists"}
        node["meta"] = legacy_meta
        manifest = valid_manifest((uid, node))

        report, catalog = validator.validate_manifest(manifest, resources=[uid])

        self.assertEqual("FAIL", report["status"], report)
        self.assertIsNone(catalog)
        self.assertIn("RESOURCE_NOT_FOUND", [error["code"] for error in report["errors"]])

        unselected_report, unselected_catalog = validator.validate_manifest(manifest)
        self.assertEqual("PASS", unselected_report["status"], unselected_report)
        self.assertEqual([], unselected_catalog["resources"])

        conflict = valid_manifest_node(uid)
        conflict["meta"] = copy.deepcopy(conflict["config"]["meta"])
        conflict["meta"]["public_gold"]["owner"] = "다른 운영팀"
        conflict_report, _ = validator.validate_manifest(valid_manifest((uid, conflict)))
        self.assertIn(
            "CONFLICTING_METADATA", [error["code"] for error in conflict_report["errors"]]
        )

    def test_non_primary_column_nullable_must_be_boolean_when_present(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        node = valid_manifest_node(uid)
        meta = node["columns"]["metric_value"]["config"]["meta"]
        meta["semantic_role"] = "label"
        meta["nullable"] = {"declared": False}
        for field in ("unit", "zero_meaning", "aggregation_behavior"):
            meta.pop(field)

        report, catalog = validator.validate_manifest(valid_manifest((uid, node)))

        self.assertEqual("FAIL", report["status"], report)
        self.assertIsNone(catalog)
        self.assertIn(
            f"nodes.{uid}.columns.metric_value.config.meta.nullable",
            [error["path"] for error in report["errors"]],
        )

    def test_nonmetric_optional_semantic_fields_reject_structured_values(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        cases = (
            ("unit", {"name": "건"}),
            ("zero_meaning", ["값이 없음"]),
            ("aggregation_behavior", {"mode": "none"}),
        )
        for field, invalid_value in cases:
            with self.subTest(field=field):
                node = valid_manifest_node(uid)
                meta = node["columns"]["metric_value"]["config"]["meta"]
                meta["semantic_role"] = "label"
                for optional in ("unit", "zero_meaning", "aggregation_behavior"):
                    meta.pop(optional)
                meta[field] = invalid_value

                report, catalog = validator.validate_manifest(valid_manifest((uid, node)))

                self.assertEqual("FAIL", report["status"], report)
                self.assertIsNone(catalog)
                self.assertIn(
                    f"nodes.{uid}.columns.metric_value.config.meta.{field}",
                    [error["path"] for error in report["errors"]],
                )

    def test_nonmetric_valid_optional_scalars_export_only_validated_scalars(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        node = valid_manifest_node(uid)
        meta = node["columns"]["metric_value"]["config"]["meta"]
        meta.update(
            {
                "aggregation_behavior": "none",
                "nullable": True,
                "semantic_role": "label",
                "unit": "코드",
                "zero_meaning": "값이 0이면 해당 코드가 없음을 뜻합니다.",
            }
        )
        node["config"]["meta"]["public_gold"]["metrics"] = {}

        report, catalog = validator.validate_manifest(valid_manifest((uid, node)))

        self.assertEqual("PASS", report["status"], report)
        exported = next(
            column for column in catalog["resources"][0]["columns"]
            if column["name"] == "metric_value"
        )["meta"]
        self.assertEqual(
            {
                "aggregation_behavior": "none",
                "null_meaning": "원천에서 지표를 제공하지 않은 상태입니다.",
                "nullable": True,
                "semantic_role": "label",
                "unit": "코드",
                "zero_meaning": "값이 0이면 해당 코드가 없음을 뜻합니다.",
            },
            exported,
        )
        self.assertTrue(all(isinstance(value, (str, bool)) for value in exported.values()))

    def test_published_producer_requires_truthful_publication_metadata_and_no_exposure(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        node = valid_manifest_node(uid, visibility="published_producer")
        report, catalog = validator.validate_manifest(valid_manifest((uid, node)))
        self.assertEqual("PASS", report["status"], report)
        exported = catalog["resources"][0]["public_gold"]
        self.assertIn("exposure_status", exported)
        self.assertEqual("none_no_live_consumer", exported["exposure_status"])
        self.assertEqual(["ai_catalog", "analyst"], exported["intended_consumer_types"])
        self.assertEqual(2, len(exported["cross_domain_usage_examples"]))

        cases = (
            ("consumers", lambda pg: pg.pop("intended_consumer_types"), "intended_consumer_types"),
            ("status", lambda pg: pg.__setitem__("exposure_status", "active_exposure"), "exposure_status"),
            ("examples_count", lambda pg: pg.__setitem__("cross_domain_usage_examples", ["한 개 예시입니다."]), "cross_domain_usage_examples"),
            ("examples_language", lambda pg: pg.__setitem__("cross_domain_usage_examples", ["English example", "두 번째 예시입니다."]), "cross_domain_usage_examples[0]"),
        )
        for name, mutate, field in cases:
            with self.subTest(name=name):
                invalid = valid_manifest_node(uid, visibility="published_producer")
                mutate(invalid["config"]["meta"]["public_gold"])
                invalid_report, invalid_catalog = validator.validate_manifest(
                    valid_manifest((uid, invalid))
                )
                self.assertEqual("FAIL", invalid_report["status"], invalid_report)
                self.assertIsNone(invalid_catalog)
                self.assertTrue(
                    any(error["path"].endswith(field) for error in invalid_report["errors"]),
                    invalid_report,
                )

        invented = valid_manifest((uid, valid_manifest_node(uid)))
        invented["exposures"]["exposure.weather.invented_app"] = valid_manifest_exposure(uid)
        invented_report, invented_catalog = validator.validate_manifest(invented)
        self.assertEqual("FAIL", invented_report["status"], invented_report)
        self.assertIsNone(invented_catalog)

    def test_internal_and_candidate_require_no_manifest_exposure(self) -> None:
        validator = manifest_validator_module()
        for visibility in ("internal", "candidate"):
            with self.subTest(visibility=visibility):
                uid = f"model.weather.gold_{visibility}"
                node = valid_manifest_node(uid, visibility=visibility)
                manifest = valid_manifest((uid, node))
                manifest["exposures"][f"exposure.weather.{visibility}"] = valid_manifest_exposure(uid)
                report, catalog = validator.validate_manifest(manifest)
                self.assertEqual("FAIL", report["status"], report)
                self.assertIsNone(catalog)
                self.assertIn("UNEXPECTED_EXPOSURE", [error["code"] for error in report["errors"]])

    def test_served_requires_real_valid_exposure_and_exports_stable_declaration(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_served"
        node = valid_manifest_node(uid, visibility="served")
        manifest = valid_manifest((uid, node))
        exposure_uid = next(iter(manifest["exposures"]))
        manifest["exposures"][exposure_uid]["owner"] = {
            "email": ["ops@example.com", "data@example.com"],
            "name": "",
        }
        report, catalog = validator.validate_manifest(manifest)
        self.assertEqual("PASS", report["status"], report)
        self.assertIn("exposures", catalog["resources"][0])
        self.assertEqual(
            [
                {
                    "maturity": "medium",
                    "name": "public_metric_application",
                    "owner": {
                        "email": ["data@example.com", "ops@example.com"],
                        "name": "",
                    },
                    "type": "application",
                    "unique_id": exposure_uid,
                }
            ],
            catalog["resources"][0]["exposures"],
        )

        for name, mutate, expected_code in (
            ("missing", lambda value: value["exposures"].clear(), "MISSING_ACTIVE_EXPOSURE"),
            ("maturity", lambda value: next(iter(value["exposures"].values())).__setitem__("maturity", "unknown"), "INVALID_EXPOSURE_MATURITY"),
            ("owner", lambda value: next(iter(value["exposures"].values())).__setitem__("owner", {"email": None, "name": ""}), "INVALID_EXPOSURE_OWNER"),
        ):
            with self.subTest(name=name):
                invalid = valid_manifest((uid, valid_manifest_node(uid, visibility="served")))
                mutate(invalid)
                invalid_report, invalid_catalog = validator.validate_manifest(invalid)
                self.assertEqual("FAIL", invalid_report["status"], invalid_report)
                self.assertIsNone(invalid_catalog)
                self.assertIn(expected_code, [error["code"] for error in invalid_report["errors"]])

    def test_join_policy_resolves_reconciliation_test_by_name_and_exports_allowlist(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        node = valid_manifest_node(uid)
        join = valid_join_metadata()
        join["source_keys"] = ["metric_value", "district_id"]
        node["config"]["meta"]["public_gold"]["joins"] = {"district_lookup": join}
        test_uid, test_node = valid_reconciliation_test(uid)
        manifest = valid_manifest((uid, node), (test_uid, test_node))

        report, catalog = validator.validate_manifest(manifest)

        self.assertEqual("PASS", report["status"], report)
        self.assertIn("joins", catalog["resources"][0]["public_gold"])
        self.assertEqual(
            {
                "district_lookup": {
                    "cardinality": "many_to_one",
                    "fan_out_policy": "대상 키가 중복되면 게시를 중단합니다.",
                    "purpose": "서울 자치구 기준 정보를 연결합니다.",
                    "reconciliation_test": "reconcile_district_join",
                    "source_keys": ["metric_value", "district_id"],
                    "target": "model.weather.dim_district",
                }
            },
            catalog["resources"][0]["public_gold"]["joins"],
        )
        self.assertNotIn(test_uid, validator.render_json(catalog))

    def test_join_policy_rejects_missing_unsafe_or_unresolved_declarations(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        cases = []
        for field in ("target", "source_keys", "purpose", "cardinality", "fan_out_policy", "reconciliation_test"):
            cases.append((f"missing_{field}", lambda join, field=field: join.pop(field), field, None))
        cases.extend(
            [
                ("one_to_many", lambda join: join.__setitem__("cardinality", "one_to_many"), "cardinality", None),
                ("many_to_many", lambda join: join.__setitem__("cardinality", "many_to_many"), "cardinality", None),
                ("unknown_source", lambda join: join.__setitem__("source_keys", ["missing_column"]), "source_keys", None),
                ("unknown_test", lambda join: join.__setitem__("reconciliation_test", "missing_test"), "reconciliation_test", None),
                ("wrong_dependency", lambda join: None, "reconciliation_test", "model.other.unrelated"),
            ]
        )
        for name, mutate, field, dependency in cases:
            with self.subTest(name=name):
                node = valid_manifest_node(uid)
                join = valid_join_metadata()
                mutate(join)
                node["config"]["meta"]["public_gold"]["joins"] = {"district_lookup": join}
                test_uid, test_node = valid_reconciliation_test(dependency or uid)
                manifest = valid_manifest((uid, node), (test_uid, test_node))
                report, catalog = validator.validate_manifest(manifest)
                self.assertEqual("FAIL", report["status"], report)
                self.assertIsNone(catalog)
                self.assertTrue(
                    any(error["path"].endswith(field) for error in report["errors"]),
                    report,
                )

    def test_lifecycle_active_and_deprecated_rules_export_only_validated_fields(self) -> None:
        validator = manifest_validator_module()
        active_uid = "model.weather.gold_active"
        active = valid_manifest_node(active_uid)
        active["config"]["meta"]["public_gold"]["lifecycle"] = {
            "replacement_is_future": True,
            "replacement_relation": "model.weather.gold_future",
            "status": "active",
        }
        deprecated_uid = "model.weather.gold_deprecated"
        deprecated = valid_manifest_node(deprecated_uid)
        deprecated["config"]["meta"]["public_gold"]["lifecycle"] = {
            "compatibility_window_guidance": "두 번의 월간 배포 동안 기존 계약을 함께 제공합니다.",
            "replacement_relation": "model.weather.gold_replacement",
            "status": "deprecated",
        }
        report, catalog = validator.validate_manifest(
            valid_manifest((deprecated_uid, deprecated), (active_uid, active))
        )
        self.assertEqual("PASS", report["status"], report)
        resources = {item["unique_id"]: item for item in catalog["resources"]}
        self.assertIn("lifecycle", resources[active_uid]["public_gold"])
        self.assertEqual(
            active["config"]["meta"]["public_gold"]["lifecycle"],
            resources[active_uid]["public_gold"]["lifecycle"],
        )
        self.assertEqual(
            deprecated["config"]["meta"]["public_gold"]["lifecycle"],
            resources[deprecated_uid]["public_gold"]["lifecycle"],
        )

    def test_lifecycle_rejects_invalid_deprecation_and_unmarked_active_replacement(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        cases = (
            ("status", {"status": "retired"}, "status"),
            ("deprecated_relation", {"status": "deprecated", "compatibility_window_guidance": "두 번의 배포 동안 호환합니다."}, "replacement_relation"),
            ("deprecated_guidance", {"status": "deprecated", "replacement_relation": "model.weather.new"}, "compatibility_window_guidance"),
            ("deprecated_english", {"status": "deprecated", "replacement_relation": "model.weather.new", "compatibility_window_guidance": "Two releases"}, "compatibility_window_guidance"),
            ("active_replacement", {"status": "active", "replacement_relation": "model.weather.future"}, "replacement_is_future"),
        )
        for name, lifecycle, field in cases:
            with self.subTest(name=name):
                node = valid_manifest_node(uid)
                node["config"]["meta"]["public_gold"]["lifecycle"] = lifecycle
                report, catalog = validator.validate_manifest(valid_manifest((uid, node)))
                self.assertEqual("FAIL", report["status"], report)
                self.assertIsNone(catalog)
                self.assertTrue(
                    any(error["path"].endswith(field) for error in report["errors"]),
                    report,
                )

    def test_reconciliation_uniqueness_is_scoped_to_same_name_dependent_tests(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        node = valid_manifest_node(uid)
        node["config"]["meta"]["public_gold"]["joins"] = {
            "district_lookup": valid_join_metadata()
        }
        dependent_uid, dependent = valid_reconciliation_test(
            uid, unique_id="test.weather.random_hash_dependent"
        )
        unrelated_uid, unrelated = valid_reconciliation_test(
            "model.other.unrelated", unique_id="test.weather.random_hash_unrelated"
        )

        report, catalog = validator.validate_manifest(
            valid_manifest((uid, node), (unrelated_uid, unrelated), (dependent_uid, dependent))
        )

        self.assertEqual("PASS", report["status"], report)
        self.assertIsNotNone(catalog)

        scenarios = (
            ("not_found", [], "RECONCILIATION_TEST_NOT_FOUND"),
            ("dependency", [(unrelated_uid, unrelated)], "RECONCILIATION_TEST_DEPENDENCY"),
            (
                "ambiguous",
                [
                    (dependent_uid, dependent),
                    valid_reconciliation_test(uid, unique_id="test.weather.second_dependent"),
                ],
                "RECONCILIATION_TEST_AMBIGUOUS",
            ),
        )
        for name, tests, expected_code in scenarios:
            with self.subTest(name=name):
                scenario_report, scenario_catalog = validator.validate_manifest(
                    valid_manifest((uid, copy.deepcopy(node)), *tests)
                )
                self.assertEqual("FAIL", scenario_report["status"], scenario_report)
                self.assertIsNone(scenario_catalog)
                self.assertIn(
                    expected_code, [error["code"] for error in scenario_report["errors"]]
                )

    def test_served_exposure_projection_rejects_paths_and_runtime_timestamps_at_exact_paths(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_served"
        cases = (
            ("uid_path", "uid", "/private/tmp/exposure", None),
            ("name_path", "name", "/private/tmp/application", ".name"),
            ("type_timestamp", "type", "2026-07-12T12:34:56Z", ".type"),
            ("owner_name_path", "owner_name", "/private/tmp/owner", ".owner.name"),
            ("owner_email_path", "owner_email", "/private/tmp/email", ".owner.email"),
            ("owner_email_timestamp", "owner_email_list", "2026-07-12T12:34:56+09:00", ".owner.email[1]"),
        )
        for name, field, value, suffix in cases:
            with self.subTest(name=name):
                manifest = valid_manifest((uid, valid_manifest_node(uid, visibility="served")))
                exposure_uid = next(iter(manifest["exposures"]))
                exposure = manifest["exposures"][exposure_uid]
                if field == "uid":
                    manifest["exposures"] = {value: exposure}
                    expected_path = f"exposures.{value}"
                elif field == "owner_name":
                    exposure["owner"] = {"email": None, "name": value}
                    expected_path = f"exposures.{exposure_uid}{suffix}"
                elif field == "owner_email":
                    exposure["owner"] = {"email": value, "name": ""}
                    expected_path = f"exposures.{exposure_uid}{suffix}"
                elif field == "owner_email_list":
                    exposure["owner"] = {
                        "email": ["ops@example.com", value],
                        "name": "",
                    }
                    expected_path = f"exposures.{exposure_uid}{suffix}"
                else:
                    exposure[field] = value
                    expected_path = f"exposures.{exposure_uid}{suffix}"
                report, catalog = validator.validate_manifest(manifest)
                self.assertEqual("FAIL", report["status"], report)
                self.assertIsNone(catalog)
                self.assertIn(expected_path, [error["path"] for error in report["errors"]])

    def test_served_exposure_valid_projection_is_byte_stable_across_mapping_order(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_served"
        forward = valid_manifest((uid, valid_manifest_node(uid, visibility="served")))
        first_uid = next(iter(forward["exposures"]))
        forward["exposures"][first_uid]["owner"] = {
            "email": ["ops@example.com", "data@example.com"],
            "name": "서비스 운영팀",
        }
        second_uid = "exposure.weather.second_app"
        forward["exposures"][second_uid] = valid_manifest_exposure(
            uid,
            name="second_application",
            owner={"email": "second@example.com", "name": ""},
        )
        reverse = copy.deepcopy(forward)
        reverse["exposures"] = dict(reversed(list(reverse["exposures"].items())))
        reverse["exposures"][first_uid]["owner"]["email"].reverse()

        forward_report, forward_catalog = validator.validate_manifest(forward)
        reverse_report, reverse_catalog = validator.validate_manifest(reverse)

        self.assertEqual("PASS", forward_report["status"], forward_report)
        self.assertEqual("PASS", reverse_report["status"], reverse_report)
        self.assertEqual(
            validator.render_json(forward_catalog).encode("utf-8"),
            validator.render_json(reverse_catalog).encode("utf-8"),
        )

    def test_exposure_timestamp_detector_covers_naive_and_compact_offsets_without_version_false_positive(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_served"
        cases = (
            ("naive", "name", "application-2026-07-12T12:34:56", ".name"),
            ("compact_offset", "type", "app-2026-07-12T12:34:56.123+0900-live", ".type"),
        )
        for name, field, value, suffix in cases:
            with self.subTest(name=name):
                manifest = valid_manifest((uid, valid_manifest_node(uid, visibility="served")))
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

    def test_time_contract_projects_valid_roles_and_rejects_timezone_or_role_conflicts(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        valid = valid_manifest((uid, valid_manifest_node(uid)))
        report, catalog = validator.validate_manifest(valid)
        self.assertEqual("PASS", report["status"], report)
        self.assertIn("time", catalog["resources"][0]["public_gold"])
        self.assertEqual(
            valid["nodes"][uid]["config"]["meta"]["public_gold"]["time"],
            catalog["resources"][0]["public_gold"]["time"],
        )

        def mutate_description(node: dict[str, object]) -> None:
            node["columns"]["product_as_of_at"]["description"] = "UTC 기준으로 계산한 제품 시각입니다."

        def add_unmapped_time_role(node: dict[str, object]) -> None:
            node["columns"]["observed_time"] = {
                "config": {"meta": {"null_meaning": "관측 시각이 없는 상태입니다.", "semantic_role": "timestamp", "time_role": "observation", "timezone": CANONICAL_TIMEZONE}},
                "data_type": "timestamp(6)",
                "description": "원천 자료를 관측한 서울 기준 시각입니다.",
                "name": "observed_time",
            }
            node["config"]["meta"]["public_gold"]["column_order"].append(
                "observed_time"
            )

        cases = (
            ("canonical_utc", lambda node: node["config"]["meta"]["public_gold"]["time"].__setitem__("canonical_timezone", "UTC"), "canonical_timezone"),
            ("role_utc", lambda node: node["config"]["meta"]["public_gold"]["time"]["roles"]["product_as_of_at"].__setitem__("timezone", "UTC"), "roles.product_as_of_at.timezone"),
            ("column_utc", lambda node: node["columns"]["product_as_of_at"]["config"]["meta"].__setitem__("timezone", "UTC"), "columns.product_as_of_at.config.meta.timezone"),
            ("role_mismatch", lambda node: node["columns"]["product_as_of_at"]["config"]["meta"].__setitem__("time_role", "event"), "columns.product_as_of_at.config.meta.time_role"),
            ("missing_role", lambda node: node["config"]["meta"]["public_gold"]["time"]["roles"].pop("published_at"), "time.roles.published_at"),
            ("utc_description", mutate_description, "columns.product_as_of_at.description"),
            ("english_slo", lambda node: node["config"]["meta"]["public_gold"]["time"].__setitem__("freshness_slo", "Within fifteen minutes"), "time.freshness_slo"),
            ("unmapped_time_role", add_unmapped_time_role, "time.roles.observed_time"),
        )
        for name, mutate, suffix in cases:
            with self.subTest(name=name):
                node = valid_manifest_node(uid)
                mutate(node)
                invalid_report, invalid_catalog = validator.validate_manifest(valid_manifest((uid, node)))
                self.assertEqual("FAIL", invalid_report["status"], invalid_report)
                self.assertIsNone(invalid_catalog)
                self.assertTrue(any(error["path"].endswith(suffix) for error in invalid_report["errors"]), invalid_report)

    def test_explicit_utc_detection_uses_ascii_identifier_boundaries(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        expected_path = f"nodes.{uid}.columns.product_as_of_at.description"
        descriptions = (
            "UTC기준으로 계산한 제품 시각입니다.",
            "UTC로 변환한 제품 시각입니다.",
            "utc에서 읽은 제품 시각입니다.",
            "제품 시각은 (UTC) 기준입니다.",
            "제품 시각은 UTC, 기준입니다.",
        )
        for description in descriptions:
            with self.subTest(description=description):
                node = valid_manifest_node(uid)
                node["columns"]["product_as_of_at"]["description"] = description
                report, catalog = validator.validate_manifest(valid_manifest((uid, node)))
                self.assertEqual("FAIL", report["status"], report)
                self.assertIsNone(catalog)
                self.assertIn(expected_path, [error["path"] for error in report["errors"]])

    def test_timestamp_data_type_and_time_role_contract_is_bidirectional(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        data_type_path = f"nodes.{uid}.columns.product_as_of_at.data_type"

        for data_type in (
            "timestamp",
            "TIMESTAMP(3)",
            "timestamp with time zone",
            "TIMESTAMP(6) WITHOUT TIME ZONE",
        ):
            with self.subTest(valid_data_type=data_type):
                node = valid_manifest_node(uid)
                node["columns"]["product_as_of_at"]["data_type"] = data_type
                report, catalog = validator.validate_manifest(valid_manifest((uid, node)))
                self.assertEqual("PASS", report["status"], report)
                self.assertIsNotNone(catalog)

        for data_type in ("varchar", "date"):
            with self.subTest(role_on_non_timestamp=data_type):
                node = valid_manifest_node(uid)
                node["columns"]["product_as_of_at"]["data_type"] = data_type
                report, catalog = validator.validate_manifest(valid_manifest((uid, node)))
                self.assertEqual("FAIL", report["status"], report)
                self.assertIsNone(catalog)
                self.assertIn(data_type_path, [error["path"] for error in report["errors"]])

        semantic_mismatch = valid_manifest_node(uid)
        semantic_mismatch["columns"]["product_as_of_at"]["config"]["meta"][
            "semantic_role"
        ] = "dimension"
        mismatch_report, mismatch_catalog = validator.validate_manifest(
            valid_manifest((uid, semantic_mismatch))
        )
        self.assertEqual("FAIL", mismatch_report["status"], mismatch_report)
        self.assertIsNone(mismatch_catalog)
        self.assertIn(
            f"nodes.{uid}.columns.product_as_of_at.config.meta.semantic_role",
            [error["path"] for error in mismatch_report["errors"]],
        )

        timestamp_without_role = valid_manifest_node(uid)
        timestamp_without_role["columns"]["event_time"] = {
            "config": {
                "meta": {
                    "null_meaning": "이벤트 시각을 기록하지 못한 상태입니다.",
                    "semantic_role": "dimension",
                }
            },
            "data_type": "TIMESTAMP(3) WITH TIME ZONE",
            "description": "원천 이벤트의 서울 기준 시각입니다.",
            "name": "event_time",
        }
        timestamp_without_role["config"]["meta"]["public_gold"][
            "column_order"
        ].append("event_time")
        missing_report, missing_catalog = validator.validate_manifest(
            valid_manifest((uid, timestamp_without_role))
        )
        self.assertEqual("FAIL", missing_report["status"], missing_report)
        self.assertIsNone(missing_catalog)
        missing_paths = [error["path"] for error in missing_report["errors"]]
        self.assertIn(
            f"nodes.{uid}.columns.event_time.config.meta.semantic_role",
            missing_paths,
        )
        self.assertIn(
            f"nodes.{uid}.config.meta.public_gold.time.roles.event_time",
            missing_paths,
        )

    def test_space_contract_requires_exact_axis_stamp_dependency_and_named_tests(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_spatial"
        node = valid_manifest_node(uid)
        test_nodes = enable_valid_space_contract(node)
        manifest = valid_manifest((uid, node), *test_nodes)
        report, catalog = validator.validate_manifest(manifest)
        self.assertEqual("PASS", report["status"], report)
        self.assertIn("space", catalog["resources"][0]["public_gold"])
        self.assertEqual(
            node["config"]["meta"]["public_gold"]["space"],
            catalog["resources"][0]["public_gold"]["space"],
        )

        portable_node = valid_manifest_node(uid)
        portable_tests = enable_valid_space_contract(portable_node)
        portable_node["depends_on"]["nodes"].remove(
            "model.asac_axes.dim_admin_dong"
        )
        portable_node["depends_on"]["nodes"].append(
            "model.alternate_axes.dim_admin_dong"
        )
        portable_report, portable_catalog = validator.validate_manifest(
            valid_manifest((uid, portable_node), *portable_tests)
        )
        self.assertEqual("PASS", portable_report["status"], portable_report)
        self.assertIsNotNone(portable_catalog)

        cases = (
            ("chain", lambda value, tests: value["config"]["meta"]["public_gold"]["space"].__setitem__("source_chain", list(reversed(CANONICAL_SPACE_SOURCE_CHAIN))), "source_chain"),
            ("key", lambda value, tests: value["config"]["meta"]["public_gold"]["space"].__setitem__("canonical_key", "source_admin_code"), "canonical_key"),
            ("missing_approved_revision", lambda value, tests: value["config"]["meta"]["public_gold"]["space"].pop("approved_revision_date"), "approved_revision_date"),
            ("wrong_approved_revision", lambda value, tests: value["config"]["meta"]["public_gold"]["space"].__setitem__("approved_revision_date", "1900-01-01"), "approved_revision_date"),
            ("stamp", lambda value, tests: value["config"]["meta"]["public_gold"]["space"].__setitem__("stamp_fields", CANONICAL_SPACE_STAMP[:-1]), "stamp_fields"),
            ("dependency", lambda value, tests: value["depends_on"]["nodes"].remove("model.asac_axes.dim_admin_dong"), "dependency"),
            ("test", lambda value, tests: tests.pop(), "reconciliation_tests"),
            ("explanation", lambda value, tests: value["config"]["meta"]["public_gold"]["space"].__setitem__("fan_out_explanation", "Stop on duplicates"), "fan_out_explanation"),
        )
        for name, mutate, suffix in cases:
            with self.subTest(name=name):
                invalid = valid_manifest_node(uid)
                invalid_tests = enable_valid_space_contract(invalid)
                mutate(invalid, invalid_tests)
                invalid_report, invalid_catalog = validator.validate_manifest(
                    valid_manifest((uid, invalid), *invalid_tests)
                )
                self.assertEqual("FAIL", invalid_report["status"], invalid_report)
                self.assertIsNone(invalid_catalog)
                self.assertTrue(any(suffix in error["path"] for error in invalid_report["errors"]), invalid_report)

    def test_metric_contract_matches_declared_metric_column_and_projects_allowlist(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        node = valid_manifest_node(uid)
        report, catalog = validator.validate_manifest(valid_manifest((uid, node)))
        self.assertEqual("PASS", report["status"], report)
        self.assertIn("metrics", catalog["resources"][0]["public_gold"])
        self.assertEqual(
            node["config"]["meta"]["public_gold"]["metrics"],
            catalog["resources"][0]["public_gold"]["metrics"],
        )

        cases = (
            ("unknown_column", lambda value: value["config"]["meta"]["public_gold"]["metrics"].__setitem__("missing_metric", value["config"]["meta"]["public_gold"]["metrics"].pop("metric_value")), "metrics.missing_metric"),
            ("formula", lambda value: value["config"]["meta"]["public_gold"]["metrics"]["metric_value"].pop("expression"), "metrics.metric_value.expression"),
            ("unit", lambda value: value["config"]["meta"]["public_gold"]["metrics"]["metric_value"].__setitem__("unit", "명"), "metrics.metric_value.unit"),
            ("aggregation", lambda value: value["config"]["meta"]["public_gold"]["metrics"]["metric_value"].__setitem__("aggregation", "avg"), "metrics.metric_value.aggregation"),
            ("zero", lambda value: value["config"]["meta"]["public_gold"]["metrics"]["metric_value"].__setitem__("zero_meaning", "다른 의미입니다."), "metrics.metric_value.zero_meaning"),
            ("null", lambda value: value["config"]["meta"]["public_gold"]["metrics"]["metric_value"].__setitem__("null_meaning", "다른 null 의미입니다."), "metrics.metric_value.null_meaning"),
            ("axes", lambda value: value["config"]["meta"]["public_gold"]["metrics"]["metric_value"].__setitem__("additive_axes", {"axis": "admin_dong"}), "metrics.metric_value.additive_axes"),
        )
        for name, mutate, suffix in cases:
            with self.subTest(name=name):
                invalid = valid_manifest_node(uid)
                mutate(invalid)
                invalid_report, invalid_catalog = validator.validate_manifest(valid_manifest((uid, invalid)))
                self.assertEqual("FAIL", invalid_report["status"], invalid_report)
                self.assertIsNone(invalid_catalog)
                self.assertTrue(any(error["path"].endswith(suffix) for error in invalid_report["errors"]), invalid_report)

    def test_metric_axes_reject_internal_duplicates_and_cross_axis_overlap(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"

        def duplicate_additive(metric: dict[str, object]) -> None:
            metric["additive_axes"] = ["admin_dong", "admin_dong"]

        def duplicate_non_additive(metric: dict[str, object]) -> None:
            metric["non_additive_axes"] = ["time", "time"]

        def overlap(metric: dict[str, object]) -> None:
            metric["non_additive_axes"] = ["admin_dong"]

        cases = (
            ("duplicate_additive", duplicate_additive, "additive_axes[1]"),
            (
                "duplicate_non_additive",
                duplicate_non_additive,
                "non_additive_axes[1]",
            ),
            ("overlap", overlap, "non_additive_axes[0]"),
        )
        for name, mutate, suffix in cases:
            with self.subTest(name=name):
                node = valid_manifest_node(uid)
                metric = node["config"]["meta"]["public_gold"]["metrics"][
                    "metric_value"
                ]
                mutate(metric)
                report, catalog = validator.validate_manifest(valid_manifest((uid, node)))
                self.assertEqual("FAIL", report["status"], report)
                self.assertIsNone(catalog)
                self.assertTrue(
                    any(error["path"].endswith(suffix) for error in report["errors"]),
                    report,
                )

    def test_quality_state_contract_validates_tokens_explanations_and_declared_columns(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_quality"
        node = valid_manifest_node(uid)
        node["columns"]["quality_state"] = {
            "config": {"meta": {"null_meaning": "품질 상태를 계산하지 못한 경우입니다.", "semantic_role": "quality_state"}},
            "data_type": "string",
            "description": "제품 품질의 안정 상태를 나타냅니다.",
            "name": "quality_state",
        }
        node["config"]["meta"]["public_gold"]["column_order"].append(
            "quality_state"
        )
        node["config"]["meta"]["public_gold"]["quality"]["state_fields"] = {
            "quality_state": {
                "allowed_values": ["complete", "missing"],
                "state_explanations": {
                    "complete": "필수 증거가 모두 확인된 상태입니다.",
                    "missing": "필수 증거가 누락된 상태입니다.",
                },
            }
        }
        report, catalog = validator.validate_manifest(valid_manifest((uid, node)))
        self.assertEqual("PASS", report["status"], report)
        self.assertIn("quality", catalog["resources"][0]["public_gold"])
        self.assertEqual(
            node["config"]["meta"]["public_gold"]["quality"],
            catalog["resources"][0]["public_gold"]["quality"],
        )

        cases = (
            ("column", lambda quality: quality["state_fields"].__setitem__("missing_column", quality["state_fields"].pop("quality_state")), "state_fields.missing_column"),
            ("token", lambda quality: quality["state_fields"]["quality_state"].__setitem__("allowed_values", ["Complete Value"]), "allowed_values"),
            ("explanation", lambda quality: quality["state_fields"]["quality_state"]["state_explanations"].__setitem__("complete", "Complete"), "state_explanations.complete"),
            ("coverage", lambda quality: quality.__setitem__("coverage_explanation", "Coverage"), "coverage_explanation"),
        )
        for name, mutate, suffix in cases:
            with self.subTest(name=name):
                invalid = copy.deepcopy(node)
                mutate(invalid["config"]["meta"]["public_gold"]["quality"])
                invalid_report, invalid_catalog = validator.validate_manifest(valid_manifest((uid, invalid)))
                self.assertEqual("FAIL", invalid_report["status"], invalid_report)
                self.assertIsNone(invalid_catalog)
                self.assertTrue(any(error["path"].endswith(suffix) for error in invalid_report["errors"]), invalid_report)

    def test_lineage_requires_five_identifier_classes_and_declared_columns_or_relation_level(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        node = valid_manifest_node(uid)
        node["config"]["meta"]["public_gold"]["lineage"]["future_unvalidated"] = {"ignored": "value"}
        report, catalog = validator.validate_manifest(valid_manifest((uid, node)))
        self.assertEqual("PASS", report["status"], report)
        self.assertIn("lineage", catalog["resources"][0]["public_gold"])
        exported = catalog["resources"][0]["public_gold"]["lineage"]
        self.assertNotIn("future_unvalidated", exported)
        self.assertEqual({"run", "raw", "request", "publication", "as_of"}, set(exported["identifiers"]))

        cases = (
            ("source", lambda lineage: lineage.__setitem__("source_relations", []), "source_relations"),
            ("class", lambda lineage: lineage["identifiers"].pop("request"), "identifiers.request"),
            ("column", lambda lineage: lineage["identifiers"]["run"].__setitem__("columns", ["missing_run_id"]), "identifiers.run.columns"),
        )
        for name, mutate, suffix in cases:
            with self.subTest(name=name):
                invalid = valid_manifest_node(uid)
                mutate(invalid["config"]["meta"]["public_gold"]["lineage"])
                invalid_report, invalid_catalog = validator.validate_manifest(valid_manifest((uid, invalid)))
                self.assertEqual("FAIL", invalid_report["status"], invalid_report)
                self.assertIsNone(invalid_catalog)
                self.assertTrue(any(error["path"].endswith(suffix) for error in invalid_report["errors"]), invalid_report)

        relation_only = valid_manifest_node(uid)
        relation_only["config"]["meta"]["public_gold"]["lineage"]["identifiers"]["run"] = {
            "columns": ["missing_run_id"],
            "relation_level_only": True,
        }
        relation_report, relation_catalog = validator.validate_manifest(valid_manifest((uid, relation_only)))
        self.assertEqual("FAIL", relation_report["status"], relation_report)
        self.assertIsNone(relation_catalog)
        self.assertIn(
            f"nodes.{uid}.config.meta.public_gold.lineage.identifiers.run.columns",
            [error["path"] for error in relation_report["errors"]],
        )

        relation_only_without_columns = valid_manifest_node(uid)
        relation_only_without_columns["config"]["meta"]["public_gold"]["lineage"]["identifiers"]["run"] = {
            "relation_level_only": True,
        }
        no_columns_report, no_columns_catalog = validator.validate_manifest(
            valid_manifest((uid, relation_only_without_columns))
        )
        self.assertEqual("PASS", no_columns_report["status"], no_columns_report)
        self.assertEqual(
            [],
            no_columns_catalog["resources"][0]["public_gold"]["lineage"]["identifiers"]["run"]["columns"],
        )

        relation_only_empty_columns = valid_manifest_node(uid)
        relation_only_empty_columns["config"]["meta"]["public_gold"]["lineage"][
            "identifiers"
        ]["run"] = {"columns": [], "relation_level_only": True}
        empty_report, empty_catalog = validator.validate_manifest(
            valid_manifest((uid, relation_only_empty_columns))
        )
        self.assertEqual("PASS", empty_report["status"], empty_report)
        self.assertEqual(
            [],
            empty_catalog["resources"][0]["public_gold"]["lineage"]["identifiers"][
                "run"
            ]["columns"],
        )


class PublicGoldCatalogComparatorTests(unittest.TestCase):
    def test_complete_fixture_passes_comparison_without_promoting_physical_proof(
        self,
    ) -> None:
        manifest, catalog = valid_catalog_pair()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manifest_path = write_json_artifact(root, "manifest.json", manifest)
            catalog_path = write_json_artifact(root, "catalog.json", catalog)

            result = run_catalog_compare_cli(
                "--manifest",
                manifest_path,
                "--catalog",
                catalog_path,
                "--require-language",
                "ko-KR",
            )

        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual("PASS", report["status"])
        self.assertEqual(
            {
                "catalog_comparison": "PASS",
                "data_contract": "NOT_RUN",
                "declared_contract": "PASS",
                "manual_semantic_review": "REQUIRED",
                "physical_contract": "NOT_RUN",
                "source_yaml_uniqueness": "NOT_RUN",
            },
            report["proof"],
        )
        self.assertEqual(
            {
                "attestation": "operator_supplied_unverified",
                "evidence_id": None,
                "evidence_kind": "fixture",
                "evidence_scope": "non_dev_fixture",
            },
            report["evidence"],
        )
        self.assertEqual("", result.stderr)
        self.assertIn("물리", result.stdout)
        self.assertNotIn("\\u", result.stdout)
        self.assertNotIn("task-3a-fixture-invocation", result.stdout)
        self.assertNotIn("generated_at", result.stdout)

    def test_catalog_differences_fail_with_stable_codes_and_exact_paths(self) -> None:
        comparator = catalog_comparator_module()
        uid = "model.weather.gold_weather_public_metric"

        def missing_relation(catalog: dict[str, object]) -> None:
            catalog["sources"][uid] = catalog["nodes"].pop(uid)

        def missing_column(catalog: dict[str, object]) -> None:
            catalog["nodes"][uid]["columns"].pop("request_id")

        def extra_column(catalog: dict[str, object]) -> None:
            catalog["nodes"][uid]["columns"]["unexpected"] = {
                "index": 8,
                "name": "unexpected",
                "type": "varchar",
            }

        def incompatible_type(catalog: dict[str, object]) -> None:
            catalog["nodes"][uid]["columns"]["metric_value"]["type"] = "varchar"

        def mismatched_order(catalog: dict[str, object]) -> None:
            columns = catalog["nodes"][uid]["columns"]
            columns["district_id"]["index"] = 2
            columns["metric_value"]["index"] = 1

        cases = (
            (
                "missing_relation",
                missing_relation,
                "MISSING_PHYSICAL_RELATION",
                f"catalog.nodes.{uid}",
            ),
            (
                "missing_column",
                missing_column,
                "MISSING_PHYSICAL_COLUMN",
                f"catalog.nodes.{uid}.columns.request_id",
            ),
            (
                "extra_column",
                extra_column,
                "EXTRA_PHYSICAL_COLUMN",
                f"catalog.nodes.{uid}.columns.unexpected",
            ),
            (
                "incompatible_type",
                incompatible_type,
                "INCOMPATIBLE_COLUMN_TYPE",
                f"catalog.nodes.{uid}.columns.metric_value.type",
            ),
            (
                "mismatched_order",
                mismatched_order,
                "PHYSICAL_COLUMN_ORDER_MISMATCH",
                f"catalog.nodes.{uid}.columns.district_id.index",
            ),
        )
        for name, mutate, expected_code, expected_path in cases:
            with self.subTest(name=name):
                manifest, catalog = valid_catalog_pair()
                mutate(catalog)
                report = comparator.compare_public_gold_catalog(manifest, catalog)
                matches = [
                    error
                    for error in report["errors"]
                    if error["code"] == expected_code
                ]
                self.assertEqual("FAIL", report["status"], report)
                self.assertEqual("PASS", report["proof"]["declared_contract"])
                self.assertEqual("FAIL", report["proof"]["catalog_comparison"])
                self.assertEqual("NOT_RUN", report["proof"]["physical_contract"])
                self.assertTrue(matches, report)
                self.assertIn(expected_path, [error["path"] for error in matches])
                self.assertTrue(all(error["uid"] == uid for error in matches))

    def test_type_normalization_is_case_whitespace_and_exact_aliases_only(self) -> None:
        comparator = catalog_comparator_module()
        uid = "model.weather.gold_weather_public_metric"
        passing_pairs = (
            ("int", " INTEGER "),
            ("double precision", " DOUBLE "),
            (" decimal ( 10 , 2 ) ", "DECIMAL(10,2)"),
        )
        for declared_type, physical_type in passing_pairs:
            with self.subTest(pass_pair=(declared_type, physical_type)):
                manifest, catalog = valid_catalog_pair()
                manifest["nodes"][uid]["columns"]["metric_value"][
                    "data_type"
                ] = declared_type
                catalog["nodes"][uid]["columns"]["metric_value"][
                    "type"
                ] = physical_type
                report = comparator.compare_public_gold_catalog(manifest, catalog)
                self.assertEqual("PASS", report["status"], report)

        failing_pairs = (
            ("decimal(10,2)", "decimal(12,2)", "metric_value"),
            ("varchar(32)", "varchar(64)", "metric_value"),
            ("int(10)", "integer(10)", "metric_value"),
            ("string", "varchar", "district_id"),
            (
                "timestamp(6)with time zone",
                "timestamp(6) with time zone",
                "metric_value",
            ),
            ("timestamp(6)", "timestamp(6) with time zone", "product_as_of_at"),
        )
        for declared_type, physical_type, column_name in failing_pairs:
            with self.subTest(fail_pair=(declared_type, physical_type)):
                manifest, catalog = valid_catalog_pair()
                manifest["nodes"][uid]["columns"][column_name][
                    "data_type"
                ] = declared_type
                catalog["nodes"][uid]["columns"][column_name][
                    "type"
                ] = physical_type
                report = comparator.compare_public_gold_catalog(manifest, catalog)
                matches = [
                    error
                    for error in report["errors"]
                    if error["code"] == "INCOMPATIBLE_COLUMN_TYPE"
                    and error["column"] == column_name
                ]
                self.assertEqual("FAIL", report["status"], report)
                self.assertTrue(matches, report)
                self.assertEqual(declared_type, matches[0]["declared_type"])
                self.assertEqual(physical_type, matches[0]["physical_type"])

    def test_invalid_catalog_and_invocation_shapes_exit_two_without_output(self) -> None:
        uid = "model.weather.gold_weather_public_metric"

        def wrong_version(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["metadata"]["dbt_schema_version"] = "catalog/v2"
            return catalog

        def top_level_list(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            return []

        def metadata_list(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["metadata"] = []
            return catalog

        def nodes_list(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["nodes"] = []
            return catalog

        def node_list(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["nodes"][uid] = []
            return catalog

        def columns_list(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["nodes"][uid]["columns"] = []
            return catalog

        def column_list(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["nodes"][uid]["columns"]["metric_value"] = []
            return catalog

        def missing_type(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["nodes"][uid]["columns"]["metric_value"].pop("type")
            return catalog

        def missing_index(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["nodes"][uid]["columns"]["metric_value"].pop("index")
            return catalog

        def string_index(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["nodes"][uid]["columns"]["metric_value"]["index"] = "2"
            return catalog

        def boolean_index(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["nodes"][uid]["columns"]["metric_value"]["index"] = True
            return catalog

        def name_mismatch(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["nodes"][uid]["columns"]["metric_value"]["name"] = "other"
            return catalog

        def nonempty_errors(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["errors"] = ["adapter failure"]
            return catalog

        def missing_manifest_invocation(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            manifest["metadata"].pop("invocation_id")
            return catalog

        def missing_catalog_invocation(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["metadata"].pop("invocation_id")
            return catalog

        def blank_manifest_invocation(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            manifest["metadata"]["invocation_id"] = "   "
            return catalog

        def blank_catalog_invocation(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["metadata"]["invocation_id"] = "   "
            return catalog

        def mismatched_invocation(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["metadata"]["invocation_id"] = "unrelated-invocation"
            return catalog

        def whitespace_mismatched_invocation(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            manifest["metadata"]["invocation_id"] = (
                " " + manifest["metadata"]["invocation_id"]
            )
            return catalog

        cases = (
            ("version", wrong_version, "UNSUPPORTED_CATALOG_VERSION", "catalog.metadata.dbt_schema_version"),
            ("top", top_level_list, "INVALID_ARTIFACT_SHAPE", "catalog"),
            ("metadata", metadata_list, "INVALID_ARTIFACT_SHAPE", "catalog.metadata"),
            ("nodes", nodes_list, "INVALID_ARTIFACT_SHAPE", "catalog.nodes"),
            ("node", node_list, "INVALID_ARTIFACT_SHAPE", "catalog.nodes"),
            ("columns", columns_list, "INVALID_ARTIFACT_SHAPE", f"catalog.nodes.{uid}.columns"),
            ("column", column_list, "INVALID_ARTIFACT_SHAPE", f"catalog.nodes.{uid}.columns"),
            ("type", missing_type, "INVALID_CATALOG_COLUMN_TYPE", f"catalog.nodes.{uid}.columns.metric_value.type"),
            ("missing_index", missing_index, "INVALID_CATALOG_COLUMN_INDEX", f"catalog.nodes.{uid}.columns.metric_value.index"),
            ("string_index", string_index, "INVALID_CATALOG_COLUMN_INDEX", f"catalog.nodes.{uid}.columns.metric_value.index"),
            ("boolean_index", boolean_index, "INVALID_CATALOG_COLUMN_INDEX", f"catalog.nodes.{uid}.columns.metric_value.index"),
            ("name", name_mismatch, "CATALOG_COLUMN_NAME_MISMATCH", f"catalog.nodes.{uid}.columns.metric_value.name"),
            ("errors", nonempty_errors, "CATALOG_ERRORS_PRESENT", "catalog.errors"),
            ("manifest_invocation", missing_manifest_invocation, "MISSING_INVOCATION_ID", "manifest.metadata.invocation_id"),
            ("catalog_invocation", missing_catalog_invocation, "MISSING_INVOCATION_ID", "catalog.metadata.invocation_id"),
            ("blank_manifest_invocation", blank_manifest_invocation, "MISSING_INVOCATION_ID", "manifest.metadata.invocation_id"),
            ("blank_catalog_invocation", blank_catalog_invocation, "MISSING_INVOCATION_ID", "catalog.metadata.invocation_id"),
            ("invocation_mismatch", mismatched_invocation, "INVOCATION_ID_MISMATCH", "catalog.metadata.invocation_id"),
            ("invocation_whitespace_mismatch", whitespace_mismatched_invocation, "INVOCATION_ID_MISMATCH", "catalog.metadata.invocation_id"),
        )
        for name, mutate, expected_code, expected_path in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary_directory:
                root = Path(temporary_directory)
                manifest, catalog = valid_catalog_pair()
                catalog_value = mutate(manifest, catalog)
                manifest_path = write_json_artifact(root, "manifest.json", manifest)
                catalog_path = write_json_artifact(root, "catalog.json", catalog_value)
                output_path = root / "report.json"
                output_path.write_text("sentinel", encoding="utf-8")
                result = run_catalog_compare_cli(
                    "--manifest", manifest_path,
                    "--catalog", catalog_path,
                    "--require-language", "ko-KR",
                    "--output", output_path,
                )
                self.assertEqual(2, result.returncode, result.stdout)
                report = json.loads(result.stdout)
                self.assertEqual("ERROR", report["status"], report)
                self.assertEqual([expected_code], [error["code"] for error in report["errors"]])
                self.assertEqual([expected_path], [error["path"] for error in report["errors"]])
                self.assertEqual("NOT_RUN", report["proof"]["catalog_comparison"])
                self.assertEqual("NOT_RUN", report["proof"]["physical_contract"])
                self.assertEqual("sentinel", output_path.read_text(encoding="utf-8"))
                self.assertEqual("", result.stderr)
                self.assertNotIn("Traceback", result.stdout)

    def test_index_shape_errors_are_distinct_from_comparison_failures(self) -> None:
        comparator = catalog_comparator_module()
        uid = "model.weather.gold_weather_public_metric"
        manifest, duplicate_catalog = valid_catalog_pair()
        duplicate_columns = duplicate_catalog["nodes"][uid]["columns"]
        duplicate_columns["metric_value"]["index"] = 1
        duplicate_report = comparator.compare_public_gold_catalog(
            manifest, duplicate_catalog
        )
        self.assertEqual("FAIL", duplicate_report["status"], duplicate_report)
        self.assertIn(
            "DUPLICATE_PHYSICAL_INDEX",
            [error["code"] for error in duplicate_report["errors"]],
        )
        self.assertIn(
            "NONCONTIGUOUS_PHYSICAL_INDEX",
            [error["code"] for error in duplicate_report["errors"]],
        )

        manifest, gap_catalog = valid_catalog_pair()
        gap_catalog["nodes"][uid]["columns"]["request_id"]["index"] = 8
        gap_report = comparator.compare_public_gold_catalog(manifest, gap_catalog)
        self.assertEqual("FAIL", gap_report["status"], gap_report)
        gap_errors = [
            error
            for error in gap_report["errors"]
            if error["code"] == "NONCONTIGUOUS_PHYSICAL_INDEX"
        ]
        self.assertEqual(
            [f"catalog.nodes.{uid}.columns.request_id.index"],
            [error["path"] for error in gap_errors],
        )
        self.assertEqual(7, gap_errors[0]["expected_index"])
        self.assertEqual(8, gap_errors[0]["physical_index"])

    def test_declared_failure_stops_catalog_and_physical_proof(self) -> None:
        comparator = catalog_comparator_module()
        manifest, catalog = valid_catalog_pair()
        uid = "model.weather.gold_weather_public_metric"
        manifest["nodes"][uid]["description"] = "English only"

        report = comparator.compare_public_gold_catalog(
            manifest,
            catalog,
            evidence_kind="approved_dev_catalog",
            evidence_id="review-144-run-7",
        )

        self.assertEqual("FAIL", report["status"], report)
        self.assertEqual("FAIL", report["proof"]["declared_contract"])
        self.assertEqual("NOT_RUN", report["proof"]["catalog_comparison"])
        self.assertEqual("NOT_RUN", report["proof"]["physical_contract"])
        self.assertEqual("NOT_RUN", report["proof"]["data_contract"])
        self.assertEqual(0, report["summary"]["difference_count"])
        self.assertEqual(0, report["summary"]["resources_checked"])

    def test_evidence_kind_controls_only_physical_artifact_proof(self) -> None:
        comparator = catalog_comparator_module()
        manifest, catalog = valid_catalog_pair()
        fixture = comparator.compare_public_gold_catalog(
            manifest, catalog, evidence_kind="fixture", evidence_id="fixture-7"
        )
        self.assertEqual("NOT_RUN", fixture["proof"]["physical_contract"])
        self.assertEqual("non_dev_fixture", fixture["evidence"]["evidence_scope"])

        missing_id = comparator.compare_public_gold_catalog(
            manifest, catalog, evidence_kind="approved_dev_catalog"
        )
        self.assertEqual("ERROR", missing_id["status"])
        self.assertEqual("MISSING_EVIDENCE_ID", missing_id["errors"][0]["code"])
        self.assertEqual("NOT_RUN", missing_id["proof"]["declared_contract"])

        approved = comparator.compare_public_gold_catalog(
            manifest,
            catalog,
            evidence_kind="approved_dev_catalog",
            evidence_id="review-144-run-7",
        )
        self.assertEqual("PASS", approved["proof"]["physical_contract"])
        self.assertEqual("NOT_RUN", approved["proof"]["data_contract"])
        self.assertEqual("REQUIRED", approved["proof"]["manual_semantic_review"])
        self.assertEqual("review-144-run-7", approved["evidence"]["evidence_id"])
        self.assertEqual(
            "operator_asserted_approved_dev_catalog",
            approved["evidence"]["evidence_scope"],
        )
        self.assertEqual(
            "operator_supplied_unverified", approved["evidence"]["attestation"]
        )
        self.assertIn("암호학적으로", approved["claim_limitations_ko"])

        failing_catalog = copy.deepcopy(catalog)
        failing_catalog["nodes"].pop("model.weather.gold_weather_public_metric")
        approved_failure = comparator.compare_public_gold_catalog(
            manifest,
            failing_catalog,
            evidence_kind="approved_dev_catalog",
            evidence_id="review-144-run-7",
        )
        self.assertEqual("FAIL", approved_failure["proof"]["physical_contract"])
        self.assertEqual("NOT_RUN", approved_failure["proof"]["data_contract"])

        valid_maximum_id = "A" + ("z" * 127)
        maximum_id_report = comparator.compare_public_gold_catalog(
            manifest,
            catalog,
            evidence_kind="approved_dev_catalog",
            evidence_id=valid_maximum_id,
        )
        self.assertEqual("PASS", maximum_id_report["status"], maximum_id_report)
        self.assertEqual(valid_maximum_id, maximum_id_report["evidence"]["evidence_id"])

        invalid_evidence_ids = (
            " review-144",
            "review-144 ",
            "review 144",
            "review\n144",
            "review/144",
            "review\\144",
            ".review-144",
            "-review-144",
            "review:144",
            "검토-144",
            "A" + ("z" * 128),
        )
        for invalid_evidence_id in invalid_evidence_ids:
            with self.subTest(invalid_evidence_id=repr(invalid_evidence_id)):
                rejected_id = comparator.compare_public_gold_catalog(
                    manifest,
                    catalog,
                    evidence_kind="approved_dev_catalog",
                    evidence_id=invalid_evidence_id,
                )
                self.assertEqual("ERROR", rejected_id["status"], rejected_id)
                self.assertEqual(
                    ["INVALID_EVIDENCE_ID"],
                    [error["code"] for error in rejected_id["errors"]],
                )
                self.assertIsNone(rejected_id["evidence"]["evidence_id"])
                self.assertEqual("NOT_RUN", rejected_id["proof"]["declared_contract"])
                self.assertEqual("NOT_RUN", rejected_id["proof"]["catalog_comparison"])
                self.assertEqual("NOT_RUN", rejected_id["proof"]["physical_contract"])

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manifest_path = write_json_artifact(root, "manifest.json", manifest)
            catalog_path = write_json_artifact(root, "catalog.json", catalog)
            output_path = root / "report.json"
            missing_id_result = run_catalog_compare_cli(
                "--manifest", manifest_path,
                "--catalog", catalog_path,
                "--require-language", "ko-KR",
                "--evidence-kind", "approved_dev_catalog",
                "--output", output_path,
            )
            self.assertEqual(2, missing_id_result.returncode, missing_id_result.stdout)
            self.assertEqual(
                "MISSING_EVIDENCE_ID",
                json.loads(missing_id_result.stdout)["errors"][0]["code"],
            )
            self.assertFalse(output_path.exists())
            self.assertEqual("", missing_id_result.stderr)

            invalid_output_path = root / "invalid-id-report.json"
            invalid_id_result = run_catalog_compare_cli(
                "--manifest", manifest_path,
                "--catalog", catalog_path,
                "--require-language", "ko-KR",
                "--evidence-kind", "approved_dev_catalog",
                "--evidence-id", "review/144",
                "--output", invalid_output_path,
            )
            self.assertEqual(2, invalid_id_result.returncode, invalid_id_result.stdout)
            invalid_id_report = json.loads(invalid_id_result.stdout)
            self.assertEqual("INVALID_EVIDENCE_ID", invalid_id_report["errors"][0]["code"])
            self.assertIsNone(invalid_id_report["evidence"]["evidence_id"])
            self.assertNotIn("review/144", invalid_id_result.stdout)
            self.assertFalse(invalid_output_path.exists())
            self.assertEqual("", invalid_id_result.stderr)

            preflight_result = run_catalog_compare_cli(
                "--manifest", root / "missing-manifest.json",
                "--catalog", catalog_path,
                "--require-language", "ko-KR",
                "--evidence-kind", "approved_dev_catalog",
                "--evidence-id", "unsafe/path",
            )
            self.assertEqual(2, preflight_result.returncode, preflight_result.stdout)
            preflight_report = json.loads(preflight_result.stdout)
            self.assertEqual("INVALID_EVIDENCE_ID", preflight_report["errors"][0]["code"])
            self.assertIsNone(preflight_report["evidence"]["evidence_id"])
            self.assertNotIn("unsafe/path", preflight_result.stdout)
            self.assertNotIn("MANIFEST_READ_ERROR", preflight_result.stdout)
            self.assertEqual("", preflight_result.stderr)

    def test_invalid_evidence_kind_uses_neutral_evidence_scope(self) -> None:
        comparator = catalog_comparator_module()
        manifest, catalog = valid_catalog_pair()

        report = comparator.compare_public_gold_catalog(
            manifest, catalog, evidence_kind="unsupported"
        )

        self.assertEqual("ERROR", report["status"], report)
        self.assertEqual("invalid_evidence_kind", report["evidence"]["evidence_scope"])
        self.assertEqual("unsupported", report["evidence"]["evidence_kind"])
        self.assertIsNone(report["evidence"]["evidence_id"])
        self.assertEqual(
            {
                "catalog_comparison": "NOT_RUN",
                "data_contract": "NOT_RUN",
                "declared_contract": "NOT_RUN",
                "manual_semantic_review": "REQUIRED",
                "physical_contract": "NOT_RUN",
                "source_yaml_uniqueness": "NOT_RUN",
            },
            report["proof"],
        )

    def test_catalog_errors_may_be_absent_or_empty_and_column_name_is_optional(self) -> None:
        comparator = catalog_comparator_module()
        uid = "model.weather.gold_weather_public_metric"
        absent = object()
        for errors_value in (absent, None, []):
            with self.subTest(errors_value=repr(errors_value)):
                manifest, catalog = valid_catalog_pair()
                if errors_value is absent:
                    catalog.pop("errors")
                else:
                    catalog["errors"] = errors_value
                catalog["nodes"][uid]["columns"]["metric_value"].pop("name")
                report = comparator.compare_public_gold_catalog(manifest, catalog)
                self.assertEqual("PASS", report["status"], report)

    def test_mapping_order_comments_and_generation_time_do_not_change_report_bytes(
        self,
    ) -> None:
        comparator = catalog_comparator_module()
        manifest, catalog = valid_catalog_pair()
        uid = "model.weather.gold_weather_public_metric"
        second_uid = "model.weather.gold_second_public_metric"
        second_node = valid_manifest_node(second_uid)
        manifest["nodes"][second_uid] = second_node
        second_catalog_node = copy.deepcopy(catalog["nodes"][uid])
        second_catalog_node["unique_id"] = second_uid
        second_catalog_node["metadata"]["name"] = second_node["name"]
        catalog["nodes"][second_uid] = second_catalog_node
        baseline = comparator.render_json(
            comparator.compare_public_gold_catalog(manifest, catalog)
        ).encode("utf-8")

        reordered_manifest = copy.deepcopy(manifest)
        reordered_manifest = dict(reversed(list(reordered_manifest.items())))
        reordered_manifest["metadata"] = dict(
            reversed(list(reordered_manifest["metadata"].items()))
        )
        reordered_manifest["nodes"] = dict(
            reversed(list(reordered_manifest["nodes"].items()))
        )
        node = reordered_manifest["nodes"][uid]
        node["columns"] = dict(reversed(list(node["columns"].items())))

        reordered_catalog = copy.deepcopy(catalog)
        reordered_catalog = dict(reversed(list(reordered_catalog.items())))
        reordered_catalog["metadata"] = dict(
            reversed(list(reordered_catalog["metadata"].items()))
        )
        reordered_catalog["metadata"]["generated_at"] = "2099-01-01T00:00:00Z"
        reordered_catalog["nodes"] = dict(
            reversed(list(reordered_catalog["nodes"].items()))
        )
        physical_node = reordered_catalog["nodes"][uid]
        physical_node["metadata"]["comment"] = "English comment is not proof"
        physical_node["columns"] = dict(
            reversed(list(physical_node["columns"].items()))
        )
        for column in physical_node["columns"].values():
            column["comment"] = "Changed catalog comment"

        reordered = comparator.render_json(
            comparator.compare_public_gold_catalog(
                reordered_manifest, reordered_catalog
            )
        ).encode("utf-8")
        self.assertEqual(baseline, reordered)
        self.assertIn("물리".encode(), reordered)
        self.assertNotIn(b"\\u", reordered)
        self.assertNotIn(b"generated_at", reordered)
        self.assertNotIn(b"Changed catalog comment", reordered)

        explicit_order_manifest = copy.deepcopy(reordered_manifest)
        explicit_order_catalog = copy.deepcopy(reordered_catalog)
        explicit_order = list(reversed(BASE_COLUMN_ORDER))
        explicit_order_manifest["nodes"][uid]["config"]["meta"]["public_gold"][
            "column_order"
        ] = explicit_order
        physical_columns = explicit_order_catalog["nodes"][uid]["columns"]
        for index, column_name in enumerate(explicit_order, start=1):
            physical_columns[column_name]["index"] = index
        explicit_report = comparator.compare_public_gold_catalog(
            explicit_order_manifest, explicit_order_catalog
        )
        self.assertEqual("PASS", explicit_report["status"], explicit_report)
        self.assertEqual(baseline, comparator.render_json(explicit_report).encode("utf-8"))

    def test_default_selection_compares_only_public_resources_and_rejects_explicit_internal(
        self,
    ) -> None:
        comparator = catalog_comparator_module()
        public_uid = "model.weather.gold_weather_public_metric"
        served_uid = "model.weather.gold_served_metric"
        internal_uid = "model.weather.gold_internal_metric"
        candidate_uid = "model.weather.gold_candidate_metric"
        manifest, catalog = valid_catalog_pair()
        served_node = valid_manifest_node(served_uid, visibility="served")
        manifest["nodes"][served_uid] = served_node
        manifest["exposures"]["exposure.weather.gold_served_metric"] = (
            valid_manifest_exposure(served_uid)
        )
        served_catalog_node = copy.deepcopy(catalog["nodes"][public_uid])
        served_catalog_node["unique_id"] = served_uid
        served_catalog_node["metadata"]["name"] = served_node["name"]
        catalog["nodes"][served_uid] = served_catalog_node
        manifest["nodes"][internal_uid] = valid_manifest_node(
            internal_uid, visibility="internal"
        )
        manifest["nodes"][candidate_uid] = valid_manifest_node(
            candidate_uid, visibility="candidate"
        )

        default_report = comparator.compare_public_gold_catalog(manifest, catalog)
        self.assertEqual("PASS", default_report["status"], default_report)
        self.assertEqual(sorted([public_uid, served_uid]), default_report["resources"])

        selected_public = comparator.compare_public_gold_catalog(
            manifest, catalog, resources=[public_uid]
        )
        self.assertEqual("PASS", selected_public["status"], selected_public)
        self.assertEqual([public_uid], selected_public["resources"])

        selected_served = comparator.compare_public_gold_catalog(
            manifest, catalog, resources=["gold_served_metric"]
        )
        self.assertEqual("PASS", selected_served["status"], selected_served)
        self.assertEqual([served_uid], selected_served["resources"])

        for selector, expected_uid in (
            (internal_uid, internal_uid),
            ("gold_candidate_metric", candidate_uid),
        ):
            with self.subTest(selector=selector):
                rejected = comparator.compare_public_gold_catalog(
                    manifest, catalog, resources=[selector]
                )
                self.assertEqual("FAIL", rejected["status"], rejected)
                self.assertEqual("PASS", rejected["proof"]["declared_contract"])
                self.assertEqual("NOT_RUN", rejected["proof"]["catalog_comparison"])
                self.assertEqual("NOT_RUN", rejected["proof"]["physical_contract"])
                self.assertEqual(
                    ["RESOURCE_NOT_PUBLISHABLE"],
                    [error["code"] for error in rejected["errors"]],
                )
                self.assertEqual(expected_uid, rejected["errors"][0]["uid"])

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
                "--manifest", manifest_path,
                "--catalog", nonfinite_path,
                "--require-language", "ko-KR",
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
                "--manifest", manifest_path,
                "--catalog", deep_path,
                "--require-language", "ko-KR",
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
                        "--manifest", manifest_path,
                        "--catalog", catalog_path,
                        "--require-language", "ko-KR",
                        "--output", output,
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
                "--manifest", manifest_path,
                "--catalog", catalog_path,
                "--require-language", "ko-KR",
                "--output", successful_output,
            )
            self.assertEqual(0, successful.returncode, successful.stdout)
            self.assertEqual(successful.stdout, successful_output.read_text(encoding="utf-8"))

            failing_catalog = copy.deepcopy(catalog)
            failing_catalog["nodes"][uid]["columns"].pop("request_id")
            failing_catalog_path = write_json_artifact(
                root, "failing-catalog.json", failing_catalog
            )
            failing_output = root / "fail-report.json"
            failing = run_catalog_compare_cli(
                "--manifest", manifest_path,
                "--catalog", failing_catalog_path,
                "--require-language", "ko-KR",
                "--output", failing_output,
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
                        "--manifest", manifest_path,
                        "--catalog", catalog_path,
                        "--require-language", "ko-KR",
                        "--output", output_path,
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
                    self.assertEqual(1, baseline_result.returncode, baseline_result.stdout)
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
                    self.assertEqual(
                        baseline["errors"], report["errors"][:-1]
                    )
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
                        "--manifest", selected_manifest,
                        "--catalog", selected_catalog,
                        "--require-language", "ko-KR",
                        "--output", output,
                    )
                    self.assertEqual(2, result.returncode, result.stdout)
                    report = json.loads(result.stdout)
                    self.assertEqual(expected_code, report["errors"][0]["code"])
                    self.assertEqual("NOT_RUN", report["proof"]["declared_contract"])
                    self.assertFalse(output.exists())
                    self.assertEqual("", result.stderr)


if __name__ == "__main__":
    unittest.main()
