"""Serving Contract v1 validation rules.

Pure functions over ``ServingModel`` records + an optional dbt manifest view.
Structural rules (required / optional / excluded / enum) are driven by
``schema.yml``; cross-model and semantic rules are coded here. Every finding is a
FAIL (CLI exit 1); invocation/IO problems are the CLI's ERROR (exit 2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from serving_contract.model import ManifestView, ServingModel

SCHEMA_PATH = Path(__file__).parent / "schema.yml"
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
INTERNAL_PUBLIC_FIELD_PARTS = (
    "raw_object_key",
    "payload_hash",
    "request_id",
    "dag_run_id",
    "source_run_id",
    "snapshot_dag_run_id",
    "representative_dag_run_id",
    "api_key",
    "service_key",
    "access_key",
    "secret",
    "token",
    "password",
    "credential",
    "email",
    "ip_address",
)


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

    # v1.3 (#600/#638): usage_patterns 항목 검증 — 스펙 밖 필드·requires 오타가 통과되지 않게.
    findings.extend(_check_usage_patterns(model, schema))
    findings.extend(_check_source_evidence(model, schema))
    findings.extend(_check_quality_coverage(model, schema))

    return findings


def _check_usage_patterns(model: ServingModel, schema: dict[str, Any]) -> list[Finding]:
    """usage_patterns(optional, v1.3) 항목 규칙 — 형은 optional 루프가, 내용은 여기가 본다.

    전역 식별자는 (product_id, pattern_id) 쌍(#638 §1)이므로 pattern_id 는 모델 안 유일성만
    강제한다. requires 어휘는 schema.yml `usage_pattern_fields.requires_allowed` 11개 고정.
    """
    findings: list[Finding] = []
    patterns = model.serving.get("usage_patterns")
    spec = schema.get("usage_pattern_fields") or {}
    if not isinstance(patterns, list) or not spec:
        return findings  # 타입 위반은 optional 루프(optional_field_invalid)가 이미 보고한다

    def add(rule: str, message: str) -> None:
        findings.append(Finding(rule, model.name, message, model.source))

    required = list(spec.get("required", []))
    known = set(required) | set(spec.get("optional", []))
    requires_allowed = set(spec.get("requires_allowed", []))
    seen_ids: set[str] = set()

    for index, pattern in enumerate(patterns):
        label = f"usage_patterns[{index}]"
        if not isinstance(pattern, dict):
            add("usage_pattern_invalid", f"{label} 은 매핑이어야 하는데 {type(pattern).__name__}")
            continue
        pattern_id = pattern.get("pattern_id")
        if isinstance(pattern_id, str) and pattern_id.strip():
            label = f"usage_patterns[{index}] '{pattern_id}'"
            if pattern_id in seen_ids:
                add("usage_pattern_duplicate", f"{label} — pattern_id 가 모델 안에서 중복")
            seen_ids.add(pattern_id)
        for field in required:
            value = pattern.get(field)
            if not isinstance(value, str) or not value.strip():
                add("usage_pattern_required_missing", f"{label} — 필수 '{field}' 누락/비문자열")
        for field in sorted(set(pattern) - known):
            add("usage_pattern_unknown_field", f"{label} — 스펙 밖 필드 '{field}' (오타 확인)")
        requires = pattern.get("requires")
        if requires is not None:
            if not isinstance(requires, list):
                add("usage_pattern_invalid", f"{label} — 'requires' 는 리스트여야 한다")
            else:
                for entry in requires:
                    if entry not in requires_allowed:
                        add("usage_pattern_requires_unknown",
                            f"{label} — requires 값 {entry!r} 은 어휘 11개(#638 §1.1)에 없다")
        if "verified_rows" in pattern and (
            isinstance(pattern["verified_rows"], bool) or not isinstance(pattern["verified_rows"], int)
        ):
            add("usage_pattern_invalid", f"{label} — 'verified_rows' 는 정수여야 한다")
        if "allow_empty" in pattern and not isinstance(pattern["allow_empty"], bool):
            add("usage_pattern_invalid", f"{label} — 'allow_empty' 는 불리언이어야 한다")

    return findings


def _is_public_https_url(value: Any) -> bool:
    """Source/licence URLs must be public HTTPS references, never credentials in disguise."""
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc) and not parsed.username and not parsed.password


def _check_source_evidence(model: ServingModel, schema: dict[str, Any]) -> list[Finding]:
    """Validate #678 source/right declarations before a Publisher can make them visible."""
    findings: list[Finding] = []
    sources = model.serving.get("source_evidence")
    spec = schema.get("source_evidence_fields") or {}
    if sources is None or not spec:
        return findings
    if not isinstance(sources, list):
        return findings  # optional type violation is already emitted by the structural loop

    def add(rule: str, message: str) -> None:
        findings.append(Finding(rule, model.name, message, model.source))

    required = tuple(spec.get("required") or ())
    known = set(required)
    allowed_redistribution = set(spec.get("redistribution_allowed") or ())
    seen_source_ids: set[str] = set()
    if not sources:
        add("source_evidence_invalid", "source_evidence 를 선언하면 최소 한 source record가 필요하다")
        return findings

    for index, source in enumerate(sources):
        label = f"source_evidence[{index}]"
        if not isinstance(source, dict):
            add("source_evidence_invalid", f"{label} 은 매핑이어야 하는데 {type(source).__name__}")
            continue
        for field in sorted(set(source) - known):
            add("source_evidence_unknown_field", f"{label} — 스펙 밖 필드 '{field}' (오타 확인)")
        missing = [field for field in required if field not in source]
        if missing:
            add("source_evidence_invalid", f"{label} — 필수 필드 누락: {missing}")

        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not IDENTIFIER_RE.fullmatch(source_id):
            add("source_evidence_invalid", f"{label}.source_id 는 식별자여야 한다")
        elif source_id in seen_source_ids:
            add("source_evidence_duplicate", f"{label}.source_id '{source_id}' 가 모델 안에서 중복")
        else:
            seen_source_ids.add(source_id)

        for field in ("source_url", "license_url"):
            if not _is_public_https_url(source.get(field)):
                add("source_evidence_invalid", f"{label}.{field} 는 인증정보 없는 public HTTPS URL이어야 한다")
        for field in ("license", "attribution"):
            if not isinstance(source.get(field), str) or not source[field].strip():
                add("source_evidence_invalid", f"{label}.{field} 는 비어 있지 않은 문자열이어야 한다")
        if source.get("redistribution") not in allowed_redistribution:
            add(
                "source_evidence_invalid",
                f"{label}.redistribution={source.get('redistribution')!r} 은 허용값 {sorted(allowed_redistribution)} 이 아니다",
            )
        checked_at = source.get("rights_checked_at")
        try:
            if not isinstance(checked_at, str):
                raise ValueError("not a string")
            date.fromisoformat(checked_at)
        except ValueError:
            add("source_evidence_invalid", f"{label}.rights_checked_at 은 YYYY-MM-DD ISO 날짜여야 한다")

    return findings


def _check_quality_coverage(model: ServingModel, schema: dict[str, Any]) -> list[Finding]:
    """Validate a reproducible distinct-coverage declaration; runtime values remain Publisher-owned."""
    findings: list[Finding] = []
    coverage = model.serving.get("quality_coverage")
    spec = schema.get("quality_coverage_fields") or {}
    if coverage is None or not spec:
        return findings
    if not isinstance(coverage, dict):
        return findings  # optional type violation is already emitted by the structural loop

    def add(rule: str, message: str) -> None:
        findings.append(Finding(rule, model.name, message, model.source))

    required = set(spec.get("required") or ())
    for field in sorted(set(coverage) - required):
        add("quality_coverage_unknown_field", f"quality_coverage — 스펙 밖 필드 '{field}' (오타 확인)")
    missing = sorted(required - set(coverage))
    if missing:
        add("quality_coverage_invalid", f"quality_coverage — 필수 필드 누락: {missing}")

    field = coverage.get("field")
    if not isinstance(field, str) or not IDENTIFIER_RE.fullmatch(field):
        add("quality_coverage_invalid", "quality_coverage.field 는 물리 컬럼 식별자여야 한다")
    elif field not in model.columns:
        add("quality_coverage_invalid", f"quality_coverage.field '{field}' 이 YAML columns 계약에 없다")
    else:
        projection = model.serving.get("public_projection")
        if isinstance(projection, dict) and field not in (projection.get("columns") or []):
            add("quality_coverage_invalid", f"quality_coverage.field '{field}' 은 public_projection에 포함돼야 한다")

    expected = coverage.get("expected_distinct_count")
    if isinstance(expected, bool) or not isinstance(expected, int) or expected < 1:
        add("quality_coverage_invalid", "quality_coverage.expected_distinct_count 는 1 이상 정수여야 한다")
    minimum_ratio = coverage.get("minimum_ratio")
    if (
        isinstance(minimum_ratio, bool)
        or not isinstance(minimum_ratio, (int, float))
        or not 0 < float(minimum_ratio) <= 1
    ):
        add("quality_coverage_invalid", "quality_coverage.minimum_ratio 는 0 초과 1 이하여야 한다")

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
    _check_public_projection(model, manifest, add)

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


def _check_public_projection(model: ServingModel, manifest: ManifestView, add) -> None:
    projection = model.serving.get("public_projection")
    if projection is None:
        return
    if not isinstance(projection, dict):
        add("public_projection_invalid", "public_projection 은 object 이어야 한다")
        return

    if set(projection) != {"schema_version", "columns"}:
        add("public_projection_invalid", "public_projection 은 schema_version 과 columns 만 선언해야 한다")

    schema_version = projection.get("schema_version")
    if not isinstance(schema_version, str) or not SEMVER_RE.fullmatch(schema_version):
        add("public_projection_invalid", "public_projection.schema_version 은 MAJOR.MINOR.PATCH 형식이어야 한다")

    columns = projection.get("columns")
    if not isinstance(columns, list) or not columns:
        add("public_projection_invalid", "public_projection.columns 는 비어 있지 않은 리스트여야 한다")
        return

    seen: set[str] = set()
    available = manifest.columns(model.name) if (manifest.supplied and manifest.has_model(model.name)) else set(model.columns)
    check_columns = bool(available)

    for column in columns:
        if not isinstance(column, str) or not IDENTIFIER_RE.fullmatch(column):
            add("public_projection_invalid", f"public_projection column {column!r} 은 물리 컬럼 식별자여야 한다")
            continue
        if column in seen:
            add("public_projection_invalid", f"public_projection column '{column}' 중복")
        seen.add(column)
        lowered = column.lower()
        if any(part in lowered for part in INTERNAL_PUBLIC_FIELD_PARTS):
            add("public_projection_internal_field", f"public_projection column '{column}' 은 내부/비밀 식별자로 공개할 수 없다")
        if check_columns and column not in available:
            add("public_projection_unknown_column", f"public_projection column '{column}' 이 모델 컬럼에 없다")
        if column not in model.columns:
            add("public_projection_unknown_column", f"public_projection column '{column}' 이 YAML columns 계약에 없다")
        else:
            _check_projected_column_metadata(model, column, add)

    required_columns = list(model.serving.get("primary_key") or [])
    if isinstance(model.serving.get("event_time"), str):
        required_columns.append(model.serving["event_time"])
    reliability = model.serving.get("reliability")
    if isinstance(reliability, dict) and isinstance(reliability.get("sample_count_field"), str):
        required_columns.append(reliability["sample_count_field"])

    projected = set(c for c in columns if isinstance(c, str))
    for required_column in required_columns:
        if required_column not in projected:
            add("public_projection_required_field_missing", f"public_projection 에 필수 컬럼 '{required_column}' 누락")


def _check_projected_column_metadata(model: ServingModel, column: str, add) -> None:
    contract = model.column_contracts.get(column) or {}
    meta = ((contract.get("config") or {}).get("meta") or {}) if isinstance(contract, dict) else {}
    required_fields = {
        "description": contract.get("description"),
        "data_type": contract.get("data_type"),
        "semantic_role": meta.get("semantic_role"),
        "nullable": meta.get("nullable") if isinstance(meta.get("nullable"), bool) else None,
        "null_meaning": meta.get("null_meaning"),
        "unit": meta.get("unit"),
    }
    missing = [field for field, value in required_fields.items() if value in (None, "")]
    if missing:
        add("public_projection_column_metadata_missing", f"public_projection column '{column}' 메타데이터 누락: {missing}")
    if "not_null" in model.columns.get(column, ()) and meta.get("nullable") is True:
        add(
            "public_projection_nullability_conflict",
            f"public_projection column '{column}' 은 not_null 테스트와 nullable=true 를 함께 선언할 수 없다",
        )


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
