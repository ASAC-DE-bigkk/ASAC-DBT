from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_STATE_MACRO = PROJECT_ROOT / "macros" / "manifest_state.sql"
WEATHER_OBSERVATION = (
    PROJECT_ROOT
    / "models"
    / "weather"
    / "special"
    / "silver"
    / "silver_kma_vilage_fcst_observation.sql"
)
WEATHER_COMPATIBILITY_SILVER = (
    PROJECT_ROOT
    / "models"
    / "weather"
    / "transform"
    / "silver"
    / "silver_kma_vilage_fcst.sql"
)
PUBLISHABLE_INPUT_CONSUMERS = (
    WEATHER_OBSERVATION,
    WEATHER_COMPATIBILITY_SILVER,
    PROJECT_ROOT
    / "models"
    / "traffic"
    / "transform"
    / "silver"
    / "silver_seoul_traffic_flow.sql",
    PROJECT_ROOT
    / "models"
    / "traffic"
    / "transform"
    / "silver"
    / "silver_seoul_traffic_incident.sql",
    PROJECT_ROOT
    / "models"
    / "traffic"
    / "transform"
    / "silver"
    / "silver_seoul_traffic_incident_current.sql",
    PROJECT_ROOT
    / "models"
    / "traffic"
    / "transform"
    / "gold"
    / "gold_traffic_incident_summary.sql",
    PROJECT_ROOT
    / "models"
    / "traffic"
    / "recovery"
    / "silver"
    / "recovery_silver_seoul_traffic_incident.sql",
)
TRAFFIC_GOLD_EVIDENCE_MODEL = (
    PROJECT_ROOT
    / "models"
    / "traffic"
    / "transform"
    / "gold"
    / "gold_traffic_incident_current_by_admin_dong_hourly.sql"
)
EFFECTIVE_MANIFEST_SINGULAR_TESTS = (
    PROJECT_ROOT
    / "tests"
    / "weather"
    / "special"
    / "assert_weather_invalid_time_observations_accounted.sql",
    PROJECT_ROOT
    / "tests"
    / "weather"
    / "transform"
    / "silver"
    / "assert_silver_kma_uses_publishable_runs.sql",
    PROJECT_ROOT
    / "tests"
    / "traffic"
    / "source"
    / "availability"
    / "assert_traffic_incident_row_availability.sql",
    PROJECT_ROOT
    / "tests"
    / "traffic"
    / "transform"
    / "silver"
    / "assert_silver_traffic_uses_publishable_runs.sql",
    PROJECT_ROOT
    / "tests"
    / "traffic"
    / "transform"
    / "silver"
    / "assert_silver_traffic_latest_publishable_record.sql",
    PROJECT_ROOT
    / "tests"
    / "traffic"
    / "transform"
    / "silver"
    / "assert_traffic_current_pinned_publishable_run.sql",
    PROJECT_ROOT
    / "tests"
    / "traffic"
    / "transform"
    / "gold"
    / "assert_gold_traffic_current_by_admin_dong_hourly_snapshot_reconciles.sql",
    PROJECT_ROOT
    / "tests"
    / "traffic"
    / "recovery"
    / "silver"
    / "assert_recovery_silver_traffic_snapshot_matches_bronze.sql",
    PROJECT_ROOT
    / "tests"
    / "traffic"
    / "recovery"
    / "gold"
    / "assert_recovery_gold_traffic_counts_match_silver.sql",
)


def compact(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").lower().split())


def normal_transform_sql(path: Path) -> str:
    sql = compact(path)
    if path != WEATHER_OBSERVATION:
        return sql
    return sql.rsplit("{% else %}", maxsplit=1)[1].split("{% endif %}", maxsplit=1)[0]


def test_latest_manifest_state_is_chosen_before_publishable_gate() -> None:
    macro = compact(MANIFEST_STATE_MACRO)

    assert "partition by cast(source_id as varchar), cast(dag_run_id as varchar)" in macro
    assert "order by cast(event_at as timestamp(6)) desc, cast(dag_id as varchar) desc" in macro
    assert "manifest_state_tie_count = 1" in macro
    assert "manifest_status = 'success'" not in macro


def test_publishable_input_consumers_gate_the_latest_manifest_state() -> None:
    for path in PUBLISHABLE_INPUT_CONSUMERS:
        sql = normal_transform_sql(path)

        assert "latest_manifest_run_state(" in sql, path
        assert "manifest_status = 'success'" in sql, path
        assert "is_publishable" in sql, path
        assert sql.index("latest_manifest_run_state(") < sql.index(
            "manifest_status = 'success'"
        ), path


def test_traffic_gold_evidence_uses_latest_manifest_state_without_status_tiebreak() -> None:
    sql = compact(TRAFFIC_GOLD_EVIDENCE_MODEL)

    assert "latest_manifest_run_state(" in sql
    assert "manifest_status desc nulls last" not in sql


def test_weather_normal_silver_consumes_the_airflow_snapshot_var() -> None:
    for path in (WEATHER_OBSERVATION, WEATHER_COMPATIBILITY_SILVER):
        sql = compact(path)

        assert "var('weather_snapshot_dag_run_id')" in sql, path
        assert "dag_run_id = '{{ snapshot_dag_run_id" in sql, path


def test_singular_contracts_verify_effective_latest_manifest_state() -> None:
    for path in EFFECTIVE_MANIFEST_SINGULAR_TESTS:
        sql = compact(path)

        assert "latest_manifest_run_state(" in sql, path
