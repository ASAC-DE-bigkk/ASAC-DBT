from pathlib import Path

import pytest
from jinja2 import Environment, nodes


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR = PROJECT_ROOT / "models" / "traffic" / "transform" / "gold"
_JINJA_ENVIRONMENT = Environment(autoescape=False)

CURRENT_EXACT_TABLE_MODELS = (
    "gold_traffic_incident_active_latest",
    "gold_traffic_incident_clearance_horizon_latest",
    "gold_traffic_incident_clearance_watchlist",
    "gold_traffic_incident_current_by_admin_dong_hourly",
    "gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily",
    "gold_traffic_incident_spatial_mapping_quality_daily",
    "gold_traffic_incident_summary",
    "gold_traffic_incident_type_mix_latest",
    "gold_traffic_incident_x_citydata_crowding_current_hourly",
    "gold_traffic_incident_x_citydata_live_context_current",
    "gold_traffic_incident_x_commerce_business_exposure_current",
    "gold_traffic_incident_x_culture_activity_daily",
    "gold_traffic_incident_x_culture_event_schedule_daily",
    "gold_traffic_incident_x_flow",
    "gold_traffic_incident_x_transit_hourly",
    "gold_traffic_incident_x_weather_current_hourly",
)

COVERAGE_HISTORY_TABLE_MODELS = (
    "gold_traffic_incident_collection_coverage_5m",
)


def _model_sql(model_name: str) -> str:
    path = GOLD_DIR / f"{model_name}.sql"
    assert path.is_file(), f"missing protected Gold model: {path}"
    return path.read_text(encoding="utf-8")


def _config_calls(sql: str) -> tuple[nodes.Call, ...]:
    parsed = _JINJA_ENVIRONMENT.parse(sql)
    return tuple(
        call
        for call in parsed.find_all(nodes.Call)
        if isinstance(call.node, nodes.Name) and call.node.name == "config"
    )


def _explicit_materializations(sql: str) -> tuple[str, ...]:
    return tuple(
        keyword.value.value.strip().lower()
        for call in _config_calls(sql)
        for keyword in call.kwargs
        if keyword.key == "materialized"
        and isinstance(keyword.value, nodes.Const)
        and isinstance(keyword.value.value, str)
    )


def _has_incremental_strategy(sql: str) -> bool:
    return any(
        keyword.key == "incremental_strategy"
        for call in _config_calls(sql)
        for keyword in call.kwargs
    )


def _assert_literal_table_config(model_name: str, sql: str) -> None:
    materialization_nodes: list[nodes.Expr] = []

    for call in _config_calls(sql):
        assert not call.args, f"{model_name}: positional config arguments are forbidden"
        assert call.dyn_args is None, (
            f"{model_name}: dynamic positional config arguments are forbidden"
        )
        assert call.dyn_kwargs is None, (
            f"{model_name}: dynamic keyword config arguments are forbidden"
        )
        for keyword in call.kwargs:
            assert keyword.key != "incremental_strategy", (
                f"{model_name}: incremental_strategy is forbidden"
            )
            if keyword.key == "materialized":
                materialization_nodes.append(keyword.value)

    assert len(materialization_nodes) == 1, (
        f"{model_name}: expected exactly one direct materialized='table' config, "
        f"got {len(materialization_nodes)}"
    )
    materialization = materialization_nodes[0]
    assert (
        isinstance(materialization, nodes.Const)
        and isinstance(materialization.value, str)
        and materialization.value.strip().lower() == "table"
    ), f"{model_name}: materialized must be the literal string 'table'"


def _assert_table_replacement(model_name: str) -> None:
    _assert_literal_table_config(model_name, _model_sql(model_name))


def test_current_exact_gold_models_remain_table_replacements() -> None:
    for model_name in CURRENT_EXACT_TABLE_MODELS:
        _assert_table_replacement(model_name)


def test_coverage_history_candidate_remains_table_until_manifest_change_interface_exists() -> None:
    for model_name in COVERAGE_HISTORY_TABLE_MODELS:
        _assert_table_replacement(model_name)


def test_materialization_parser_handles_jinja_trim_markers_and_whitespace() -> None:
    sql = (
        "{{- config(tags=['value)'], materialized = \"incremental\") -}}\n"
        "select 1"
    )

    assert _explicit_materializations(sql) == ("incremental",)


def test_materialization_parser_treats_jinja_inside_sql_comments_as_active() -> None:
    sql = """
    -- {{ config(materialized='incremental') }}
    /* {{- config(incremental_strategy='merge') -}} */
    {{ config(materialized='table') }}
    select 1
    """

    assert _explicit_materializations(sql) == ("incremental", "table")
    assert _has_incremental_strategy(sql)


def test_materialization_parser_ignores_jinja_comments() -> None:
    sql = "{# {{ config(materialized='incremental') }} #}\nselect 1"

    assert _explicit_materializations(sql) == ()


def test_protected_model_uses_direct_table_config_instead_of_project_default() -> None:
    sql = _model_sql("gold_traffic_incident_summary")

    assert _explicit_materializations(sql) == ("table",)


@pytest.mark.parametrize(
    "sql",
    (
        "{{ config(materialized=var('materialization')) }} select 1",
        "{{ config({'materialized': 'incremental'}) }} select 1",
        "{{ config(**model_config) }} select 1",
        (
            "{{ config(materialized='table') }}\n"
            "{{ config(materialized='incremental') }}\nselect 1"
        ),
        "{{ config(materialized='table', incremental_strategy='merge') }} select 1",
    ),
)
def test_materialization_guard_fails_closed_on_competing_or_dynamic_config(
    sql: str,
) -> None:
    with pytest.raises(AssertionError):
        _assert_literal_table_config("fixture_model", sql)
