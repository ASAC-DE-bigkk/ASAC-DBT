from __future__ import annotations

import copy as copy
import importlib
import io as io
import json
import os as os
import tempfile as tempfile
import textwrap as textwrap
import unittest as unittest
from pathlib import Path

from contracts.engine import lint_schema_contract_source as _lint_schema_contract_source
from contracts.engine.tests.capabilities import (
    requires_symlink_capability as requires_symlink_capability,
)
from contracts.engine.tests.cli_fixtures import (
    CATALOG_COMPARE_SCRIPT as CATALOG_COMPARE_SCRIPT,
    ENGINE_ROOT as ENGINE_ROOT,
    MANIFEST_SCRIPT as MANIFEST_SCRIPT,
    REPO_ROOT as REPO_ROOT,
    SCRIPT as SCRIPT,
    run_catalog_compare_cli as run_catalog_compare_cli,
    run_cli as run_cli,
    run_cli_bytes as run_cli_bytes,
    run_manifest_cli as run_manifest_cli,
    write_yaml as write_yaml,
)


lint = _lint_schema_contract_source


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
                "config": {
                    "meta": {
                        "null_meaning": "실행 식별자가 없는 상태입니다.",
                        "semantic_role": "lineage_id",
                    }
                },
                "data_type": "string",
                "description": "원천 실행을 추적하는 DAG 실행 식별자입니다.",
                "name": "dag_run_id",
            },
            "product_as_of_at": {
                "config": {
                    "meta": {
                        "null_meaning": "제품 기준 시각을 계산할 수 없는 상태입니다.",
                        "semantic_role": "timestamp",
                        "time_role": "as_of",
                        "timezone": CANONICAL_TIMEZONE,
                    }
                },
                "data_type": "timestamp(6)",
                "description": "제품이 반영한 최신 증거의 서울 기준 시각입니다.",
                "name": "product_as_of_at",
            },
            "published_at": {
                "config": {
                    "meta": {
                        "null_meaning": "게시 시각을 기록하지 못한 상태입니다.",
                        "semantic_role": "timestamp",
                        "time_role": "publication",
                        "timezone": CANONICAL_TIMEZONE,
                    }
                },
                "data_type": "timestamp(6)",
                "description": "제품을 게시한 서울 기준 시각입니다.",
                "name": "published_at",
            },
            "raw_object_key": {
                "config": {
                    "meta": {
                        "null_meaning": "원본 객체를 연결할 수 없는 상태입니다.",
                        "semantic_role": "lineage_id",
                    }
                },
                "data_type": "string",
                "description": "원본 객체를 추적하는 안정 식별자입니다.",
                "name": "raw_object_key",
            },
            "request_id": {
                "config": {
                    "meta": {
                        "null_meaning": "요청 식별자가 없는 상태입니다.",
                        "semantic_role": "lineage_id",
                    }
                },
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
        {"email": None, "name": "서울 서비스팀"} if owner is OWNER_MISSING else owner
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
            "data_type": "date"
            if column_name == "admin_dong_revision_date"
            else "string",
            "description": f"정본 공간축의 {column_name} 값을 설명하는 열입니다.",
            "name": column_name,
        }
    node["config"]["meta"]["public_gold"]["column_order"].extend(CANONICAL_SPACE_STAMP)
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
            exposure_uid = (
                f"exposure.weather.{node.get('name', uid.rsplit('.', 1)[-1])}"
            )
            exposures[exposure_uid] = valid_manifest_exposure(uid)
    return {
        "exposures": exposures,
        "metadata": {
            "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v12.json"
        },
        "nodes": manifest_nodes,
    }


def write_manifest(
    root: Path, manifest: object, *, name: str = "manifest.json"
) -> Path:
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
    return importlib.import_module("contracts.engine.validate_public_gold_manifest")


def catalog_comparator_module():
    return importlib.import_module("contracts.engine.compare_public_gold_catalog")


def errors_with_code(report: dict[str, object], code: str) -> list[dict[str, object]]:
    return [error for error in report["errors"] if error["code"] == code]
