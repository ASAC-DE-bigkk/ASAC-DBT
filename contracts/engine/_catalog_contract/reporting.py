"""Internal _catalog_contract reporting responsibility."""

from __future__ import annotations

import re
from typing import Iterable

from contracts.engine._manifest_contract import foundation as manifest_validator

EVIDENCE_KINDS = {"fixture", "approved_dev_catalog"}


EVIDENCE_SCOPES = {
    "approved_dev_catalog": "operator_asserted_approved_dev_catalog",
    "fixture": "non_dev_fixture",
}


EVIDENCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


CLAIM_LIMITATIONS_KO = (
    "이 검사는 제공된 dbt catalog 아티팩트의 물리 컬럼·타입·순서를 선언과 비교할 뿐, "
    "승인 또는 dev warehouse 실행을 암호학적으로 확인하지 않습니다. catalog 주석, "
    "SQL projection, grain, 최신 행 선택, reconciliation, 데이터 값 또는 의미적 진실성도 "
    "증명하지 않습니다."
)


def _error(code: str, path: str, message: str, **details: object) -> dict[str, object]:
    result: dict[str, object] = {"code": code, "message": message, "path": path}
    result.update(details)
    return result


def _evidence(evidence_kind: str, evidence_id: str | None) -> dict[str, object]:
    return {
        "attestation": "operator_supplied_unverified",
        "evidence_id": evidence_id,
        "evidence_kind": evidence_kind,
        "evidence_scope": EVIDENCE_SCOPES.get(evidence_kind, "invalid_evidence_kind"),
    }


def _validate_evidence_argument(
    evidence_kind: str, evidence_id: object
) -> tuple[str | None, dict[str, object] | None]:
    normalized_evidence_id = evidence_id if isinstance(evidence_id, str) else None
    if evidence_kind not in EVIDENCE_KINDS:
        return None, _error("CLI_ERROR", "evidence_kind", "unsupported evidence kind")
    if evidence_kind == "approved_dev_catalog" and not normalized_evidence_id:
        return None, _error(
            "MISSING_EVIDENCE_ID",
            "evidence_id",
            "approved_dev_catalog requires a nonempty evidence ID",
        )
    if normalized_evidence_id is not None and not EVIDENCE_ID_RE.fullmatch(
        normalized_evidence_id
    ):
        return None, _error(
            "INVALID_EVIDENCE_ID",
            "evidence_id",
            "evidence ID must match ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
        )
    return normalized_evidence_id, None


def _proof(
    declared_status: str,
    comparison_status: str,
    evidence_kind: str,
    evidence_id: str | None,
) -> dict[str, str]:
    physical_status = "NOT_RUN"
    if (
        declared_status == "PASS"
        and comparison_status in {"PASS", "FAIL"}
        and evidence_kind == "approved_dev_catalog"
        and evidence_id
    ):
        physical_status = comparison_status
    return {
        "catalog_comparison": comparison_status,
        "data_contract": "NOT_RUN",
        "declared_contract": declared_status,
        "manual_semantic_review": "REQUIRED",
        "physical_contract": physical_status,
        "source_yaml_uniqueness": "NOT_RUN",
    }


def _report(
    status: str,
    errors: Iterable[dict[str, object]],
    *,
    declared_status: str,
    comparison_status: str,
    evidence_kind: str,
    evidence_id: str | None,
    required_language: str,
    resources: Iterable[str] = (),
) -> dict[str, object]:
    ordered_errors = sorted(
        errors,
        key=lambda item: (
            str(item.get("path", "")),
            str(item.get("code", "")),
            str(item.get("column", "")),
            str(item.get("message", "")),
        ),
    )
    selected_resources = sorted(set(resources))
    return {
        "claim_limitations_ko": CLAIM_LIMITATIONS_KO,
        "errors": ordered_errors,
        "evidence": _evidence(evidence_kind, evidence_id),
        "proof": _proof(declared_status, comparison_status, evidence_kind, evidence_id),
        "proof_scope": "supplied_dbt_catalog_artifact_comparison",
        "required_language": required_language,
        "resources": selected_resources,
        "status": status,
        "summary": {
            "difference_count": (
                len(ordered_errors) if comparison_status == "FAIL" else 0
            ),
            "error_count": len(ordered_errors) if status == "ERROR" else 0,
            "resources_checked": (
                len(selected_resources) if comparison_status in {"PASS", "FAIL"} else 0
            ),
        },
    }


def _with_output_error(
    report: dict[str, object], output_error: dict[str, object]
) -> dict[str, object]:
    updated = dict(report)
    updated["errors"] = [*report.get("errors", []), output_error]
    summary = dict(report.get("summary", {}))
    summary["error_count"] = int(summary.get("error_count", 0)) + 1
    updated["summary"] = summary
    updated["status"] = "ERROR"
    return updated


def render_json(value: object) -> str:
    return manifest_validator.render_json(value)
