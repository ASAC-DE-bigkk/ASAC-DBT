"""Serving Contract v1 validation rules.

Pure functions over ``ServingModel`` records + an optional dbt manifest view.
Structural rules (required / optional / excluded / enum) are driven by
``schema.yml``; cross-model and semantic rules are coded here. Every finding is a
FAIL (CLI exit 1); invocation/IO problems are the CLI's ERROR (exit 2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from serving_contract.model import ManifestView, ServingModel

SCHEMA_PATH = Path(__file__).parent / "schema.yml"


@dataclass(frozen=True)
class Finding:
    rule: str
    model: str
    message: str
    source: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"rule": self.rule, "model": self.model, "message": self.message, "source": self.source}


@dataclass
class ValidationResult:
    findings: list[Finding]
    models_checked: int

    @property
    def ok(self) -> bool:
        return not self.findings


def load_schema(path: str | Path = SCHEMA_PATH) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _type_ok(value: Any, spec: dict[str, Any]) -> bool:
    kind = spec.get("type")
    if kind == "bool":
        return isinstance(value, bool)
    if kind == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "string":
        return isinstance(value, str)
    if kind == "list":
        return isinstance(value, list)
    if kind in {"object"}:
        return isinstance(value, dict)
    if kind == "enum":
        return True  # enum membership checked separately
    return True


def _validate_value(field: str, value: Any, spec: dict[str, Any], *, required: bool) -> list[tuple[str, str]]:
    """Return (rule_id, message) violations for one declared field value."""
    out: list[tuple[str, str]] = []
    base_rule = "required_field_invalid" if required else "optional_field_invalid"

    if spec.get("type") == "enum":
        allowed = spec.get("allowed", [])
        if value not in allowed:
            out.append(("invalid_enum_value", f"'{field}'={value!r} 은 허용값 {allowed} 이 아니다"))
        return out

    if not _type_ok(value, spec):
        out.append((base_rule, f"'{field}' 타입이 {spec.get('type')} 이어야 하는데 {type(value).__name__}"))
        return out

    if spec.get("non_empty") and isinstance(value, str) and not value.strip():
        out.append((base_rule, f"'{field}' 이 비어 있다"))
    if spec.get("pattern") and isinstance(value, str) and not re.fullmatch(spec["pattern"], value):
        out.append(("invalid_field_format", f"'{field}'={value!r} 이 형식 {spec['pattern']} 과 불일치"))
    if spec.get("min_items") and isinstance(value, list) and len(value) < spec["min_items"]:
        out.append((base_rule, f"'{field}' 은 최소 {spec['min_items']}개 항목이 필요하다"))
    if spec.get("min") is not None and isinstance(value, int) and value < spec["min"]:
        out.append((base_rule, f"'{field}'={value} 은 최소 {spec['min']} 이상이어야 한다"))
    return out


def _check_structural(model: ServingModel, schema: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    serving = model.serving

    def add(rule: str, message: str) -> None:
        findings.append(Finding(rule, model.name, message, model.source))

    # Required presence + value validity.
    for field, spec in schema["required"].items():
        if field not in serving:
            add("required_field_missing", f"필수 필드 '{field}' 누락")
            continue
        for rule, message in _validate_value(field, serving[field], spec, required=True):
            add(rule, message)

    # Optional value validity (only when present).
    for field, spec in schema.get("optional", {}).items():
        if field in serving:
            for rule, message in _validate_value(field, serving[field], spec, required=False):
                add(rule, message)

    # Excluded fields must not appear under meta.serving.
    for field in schema.get("excluded", []):
        if field in serving:
            add("excluded_field_present", f"'{field}' 은 계약에 선언할 수 없다 (실측/Worker 소유)")

    # Legacy meta keys alongside meta.serving == double declaration.
    for key in schema.get("legacy_meta_keys", []):
        if key in model.meta:
            add("legacy_double_declaration", f"구 메타 'meta.{key}' 와 신규 'meta.serving' 이중 선언")

    # v1.1 conditional requirement: declaring `if_present` obligates `then_required`.
    for rule in schema.get("conditional_required", []):
        trigger, needed = rule.get("if_present"), rule.get("then_required")
        if trigger and needed and trigger in serving and needed not in serving:
            add("conditional_required_missing", f"'{trigger}' 선언 제품은 '{needed}' 필수 (v1.1)")

    return findings


def _check_semantic(model: ServingModel, manifest: ManifestView) -> list[Finding]:
    findings: list[Finding] = []
    serving = model.serving

    def add(rule: str, message: str) -> None:
        findings.append(Finding(rule, model.name, message, model.source))

    # external=true 인데 enabled 이 true 가 아님.
    if serving.get("external") is True and serving.get("enabled") is not True:
        add("external_enabled_conflict", "external=true 인데 enabled 이 true 가 아니다 (게시 안 되는데 공개 노출)")

    # publication_trigger 는 cron 또는 asset 정확히 하나.
    if "upsert_strategy" in serving and serving.get("publication_mode") != "upsert":
        add("upsert_strategy_invalid", "upsert_strategy requires publication_mode=upsert")

    trigger = serving.get("publication_trigger")
    if isinstance(trigger, dict):
        has_cron = "schedule_cron" in trigger
        has_asset = "trigger_type" in trigger or "max_interval_minutes" in trigger
        if has_cron and has_asset:
            add("publication_trigger_invalid", "publication_trigger 에 cron 과 asset 이 함께 선언됨")
        elif not has_cron and not has_asset:
            add("publication_trigger_invalid", "publication_trigger 에 schedule_cron 또는 (trigger_type+max_interval_minutes) 필요")
        elif has_asset:
            if trigger.get("trigger_type") != "asset":
                add("publication_trigger_invalid", "asset 트리거는 trigger_type: asset 이어야 한다")
            if "max_interval_minutes" not in trigger:
                add("publication_trigger_invalid", "asset 트리거는 max_interval_minutes 를 선언해야 한다")
    elif trigger is not None:
        add("publication_trigger_invalid", "publication_trigger 는 object 이어야 한다")

    # partial_policy.min_publish_ratio 는 0~1.
    partial = serving.get("partial_policy")
    if isinstance(partial, dict):
        ratio = partial.get("min_publish_ratio")
        if ratio is None or not isinstance(ratio, (int, float)) or isinstance(ratio, bool) or not (0 <= ratio <= 1):
            add("partial_policy_invalid", f"partial_policy.min_publish_ratio 는 0~1 이어야 한다 (현재 {ratio!r})")

    # reliability (rollup 전용) — 있으면 3개 키 + 정책 enum.
    reliability = serving.get("reliability")
    if isinstance(reliability, dict):
        for key in ("sample_count_field", "minimum_sample_count", "insufficient_sample_policy"):
            if key not in reliability:
                add("reliability_invalid", f"reliability.{key} 누락")
        policy = reliability.get("insufficient_sample_policy")
        allowed = {"suppress_row", "flag_degraded", "allow"}
        if policy is not None and policy not in allowed:
            add("reliability_invalid", f"insufficient_sample_policy={policy!r} 은 {sorted(allowed)} 이 아니다")

    # primary_key 컬럼 실존 + not_null·고유성 근거.
    _check_primary_key(model, manifest, add)

    # manifest 멤버십.
    if manifest.supplied and not manifest.has_model(model.name):
        add("model_not_in_manifest", "계약에 선언됐으나 dbt manifest 에 없는 모델")

    return findings


def _check_primary_key(model: ServingModel, manifest: ManifestView, add) -> None:
    pk = model.serving.get("primary_key")
    if not isinstance(pk, list) or not pk:
        return  # structural rule already flagged missing/typed primary_key

    available = manifest.columns(model.name) if (manifest.supplied and manifest.has_model(model.name)) else set(model.columns)
    check_columns = bool(available)

    for col in pk:
        if check_columns and col not in available:
            add("primary_key_not_a_column", f"primary_key '{col}' 이 모델 컬럼에 없다")
        if "not_null" not in model.columns.get(col, ()):  # not_null 근거는 yml 컬럼 테스트로 확인
            add("primary_key_evidence_missing", f"primary_key '{col}' 에 not_null 테스트 근거 없음")

    if len(pk) == 1:
        col = pk[0]
        if "unique" not in model.columns.get(col, ()):
            add("primary_key_evidence_missing", f"단일 primary_key '{col}' 에 unique 테스트 근거 없음")
    else:
        combined = any("unique_combination" in t for tests in model.columns.values() for t in tests)
        combined = combined or any("unique_combination" in t for t in model.model_tests)
        if not combined:
            add("primary_key_evidence_missing", f"복합 primary_key {pk} 에 조합 고유성(unique_combination_of_columns) 근거 없음")


def _check_global(models: list[ServingModel]) -> list[Finding]:
    findings: list[Finding] = []
    seen: dict[str, ServingModel] = {}
    for model in models:
        pid = model.serving.get("product_id")
        if not isinstance(pid, str) or not pid:
            continue
        if pid in seen:
            findings.append(
                Finding(
                    "product_id_duplicate",
                    model.name,
                    f"product_id '{pid}' 가 '{seen[pid].name}' 와 중복 (전역 유일 위반)",
                    model.source,
                )
            )
        else:
            seen[pid] = model
    return findings


def validate(models: list[ServingModel], manifest: ManifestView | None = None, schema: dict[str, Any] | None = None) -> ValidationResult:
    """Run all serving-contract rules and return a deterministic result."""
    manifest = manifest or ManifestView(supplied=False)
    schema = schema or load_schema()

    findings: list[Finding] = []
    for model in models:
        findings.extend(_check_structural(model, schema))
        findings.extend(_check_semantic(model, manifest))
    findings.extend(_check_global(models))

    findings.sort(key=lambda f: (f.source, f.model, f.rule, f.message))
    return ValidationResult(findings=findings, models_checked=len(models))
