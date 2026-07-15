"""Internal _manifest_contract semantic_rules responsibility."""

from __future__ import annotations

from typing import Mapping

from .foundation import (
    MISSING,
    STABLE_ENUM_TOKEN_RE,
    _error,
)

from .metadata import (
    _korean_text,
    _nonempty_string,
    _validated_string_list,
)


def _validate_metrics(
    value: object,
    path: str,
    column_names: set[str],
    column_meta: Mapping[str, Mapping[str, object]],
) -> tuple[list[dict[str, str]], dict[str, object]]:
    errors: list[dict[str, str]] = []
    projection: dict[str, object] = {}
    if not isinstance(value, dict):
        return errors, projection
    metric_columns = {
        name
        for name, meta in column_meta.items()
        if meta.get("semantic_role") == "metric"
    }
    for metric_name in sorted(metric_columns - set(value)):
        errors.append(
            _error(
                "MISSING_METRIC_CONTRACT",
                f"{path}.{metric_name}",
                "every declared metric column requires a metric contract",
            )
        )
    for metric_name in sorted(value, key=str):
        metric_path = f"{path}.{metric_name}"
        metric_value = value[metric_name]
        if not isinstance(metric_name, str) or not isinstance(metric_value, dict):
            errors.append(
                _error(
                    "INVALID_METRIC",
                    metric_path,
                    "metric entries must be named mappings",
                )
            )
            continue
        if metric_name not in column_names or metric_name not in metric_columns:
            errors.append(
                _error(
                    "UNKNOWN_METRIC_COLUMN",
                    metric_path,
                    "metric contract must name a declared metric column",
                )
            )
        projected_metric: dict[str, object] = {}
        expression_present = False
        for expression_field in ("expression", "formula", "source_expression"):
            if expression_field not in metric_value:
                continue
            expression = _nonempty_string(
                metric_value,
                expression_field,
                f"{metric_path}.{expression_field}",
                errors,
            )
            if expression is not None:
                expression_present = True
                projected_metric[expression_field] = expression
        if not expression_present:
            errors.append(
                _error(
                    "MISSING_METRIC_EXPRESSION",
                    f"{metric_path}.expression",
                    "metric requires an expression, formula, or source_expression",
                )
            )

        validated_scalars: dict[str, str] = {}
        for field in ("unit", "aggregation", "denominator"):
            scalar = _nonempty_string(
                metric_value, field, f"{metric_path}.{field}", errors
            )
            if scalar is not None:
                validated_scalars[field] = scalar
                projected_metric[field] = scalar
        for field in ("zero_meaning", "null_meaning"):
            text = _korean_text(metric_value, field, f"{metric_path}.{field}", errors)
            if text is not None:
                validated_scalars[field] = text
                projected_metric[field] = text
        axis_values: dict[str, list[str]] = {}
        for field in ("additive_axes", "non_additive_axes"):
            raw_axes = metric_value.get(field, MISSING)
            axes = _validated_string_list(
                raw_axes,
                f"{metric_path}.{field}",
                errors,
                minimum=0,
            )
            projected_metric[field] = axes
            axis_values[field] = axes
            if isinstance(raw_axes, list):
                seen_axes: set[str] = set()
                for index, raw_axis in enumerate(raw_axes):
                    if not isinstance(raw_axis, str) or not raw_axis.strip():
                        continue
                    axis = raw_axis.strip()
                    if axis in seen_axes:
                        errors.append(
                            _error(
                                "DUPLICATE_METRIC_AXIS",
                                f"{metric_path}.{field}[{index}]",
                                "metric axis lists must not contain duplicates",
                            )
                        )
                    seen_axes.add(axis)

        overlapping_axes = set(axis_values["additive_axes"]) & set(
            axis_values["non_additive_axes"]
        )
        raw_non_additive = metric_value.get("non_additive_axes", MISSING)
        if overlapping_axes and isinstance(raw_non_additive, list):
            for index, raw_axis in enumerate(raw_non_additive):
                if isinstance(raw_axis, str) and raw_axis.strip() in overlapping_axes:
                    errors.append(
                        _error(
                            "METRIC_AXIS_OVERLAP",
                            f"{metric_path}.non_additive_axes[{index}]",
                            "an axis cannot be both additive and non-additive",
                        )
                    )

        meta = column_meta.get(metric_name, {})
        for contract_field, meta_field in (
            ("unit", "unit"),
            ("aggregation", "aggregation_behavior"),
            ("zero_meaning", "zero_meaning"),
            ("null_meaning", "null_meaning"),
        ):
            contract_value = validated_scalars.get(contract_field)
            if contract_value is not None and meta.get(meta_field) != contract_value:
                errors.append(
                    _error(
                        "METRIC_METADATA_MISMATCH",
                        f"{metric_path}.{contract_field}",
                        f"metric {contract_field} must match column {meta_field}",
                    )
                )
        projection[metric_name] = projected_metric
    return errors, projection


def _validate_quality(
    value: object, path: str, column_names: set[str]
) -> tuple[list[dict[str, str]], dict[str, object]]:
    errors: list[dict[str, str]] = []
    projection: dict[str, object] = {}
    if not isinstance(value, dict):
        return errors, projection
    for field in (
        "completeness_explanation",
        "freshness_explanation",
        "coverage_explanation",
    ):
        text = _korean_text(value, field, f"{path}.{field}", errors)
        if text is not None:
            projection[field] = text

    state_fields_value = value.get("state_fields", MISSING)
    if not isinstance(state_fields_value, dict):
        errors.append(
            _error(
                "INVALID_TYPE", f"{path}.state_fields", "state_fields must be a mapping"
            )
        )
        state_fields: Mapping[str, object] = {}
    else:
        state_fields = state_fields_value
    projected_states: dict[str, object] = {}
    for column_name in sorted(state_fields, key=str):
        state_path = f"{path}.state_fields.{column_name}"
        state_value = state_fields[column_name]
        if not isinstance(column_name, str) or not isinstance(state_value, dict):
            errors.append(
                _error(
                    "INVALID_QUALITY_STATE",
                    state_path,
                    "quality state entries must be named mappings",
                )
            )
            continue
        if column_name not in column_names:
            errors.append(
                _error(
                    "UNKNOWN_QUALITY_COLUMN",
                    state_path,
                    "quality state must name a declared model column",
                )
            )
        allowed_value = state_value.get("allowed_values", MISSING)
        tokens: list[str] = []
        if (
            not isinstance(allowed_value, list)
            or not allowed_value
            or any(
                not isinstance(token, str) or not STABLE_ENUM_TOKEN_RE.fullmatch(token)
                for token in allowed_value
            )
            or len(set(allowed_value)) != len(allowed_value)
        ):
            errors.append(
                _error(
                    "INVALID_ENUM_TOKENS",
                    f"{state_path}.allowed_values",
                    "allowed_values must contain distinct stable lowercase enum tokens",
                )
            )
        else:
            tokens = sorted(allowed_value)

        explanations_value = state_value.get("state_explanations", MISSING)
        if not isinstance(explanations_value, dict):
            errors.append(
                _error(
                    "INVALID_TYPE",
                    f"{state_path}.state_explanations",
                    "state_explanations must be a mapping",
                )
            )
            explanations: Mapping[str, object] = {}
        else:
            explanations = explanations_value
        if set(explanations) != set(tokens):
            errors.append(
                _error(
                    "STATE_EXPLANATION_MISMATCH",
                    f"{state_path}.state_explanations",
                    "state explanations must exactly cover allowed_values",
                )
            )
        projected_explanations: dict[str, str] = {}
        for token in tokens:
            explanation = _korean_text(
                explanations,
                token,
                f"{state_path}.state_explanations.{token}",
                errors,
            )
            if explanation is not None:
                projected_explanations[token] = explanation
        projected_states[column_name] = {
            "allowed_values": tokens,
            "state_explanations": projected_explanations,
        }
    projection["state_fields"] = projected_states
    return errors, projection
