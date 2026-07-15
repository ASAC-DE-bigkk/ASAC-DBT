from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRAFFIC_MODELS = PROJECT_ROOT / "models" / "traffic"
TRAFFIC_TESTS = Path(__file__).resolve().parent


def model_sql(model_name: str) -> Path:
    matches = list(TRAFFIC_MODELS.rglob(f"{model_name}.sql"))
    assert len(matches) == 1, (
        f"expected one Traffic model named {model_name}: {matches}"
    )
    return matches[0]


def singular_sql(filename: str) -> Path:
    matches = list(TRAFFIC_TESTS.rglob(filename))
    assert len(matches) == 1, (
        f"expected one Traffic singular test named {filename}: {matches}"
    )
    return matches[0]


def test_dbt_project_disables_static_parser_for_deterministic_dependency_edges():
    project = (PROJECT_ROOT / "dbt_project.yml").read_text(encoding="utf-8")

    assert "static_parser: false" in project


def test_current_model_requires_transform_pinned_publishable_manifest_run():
    sql = model_sql("silver_seoul_traffic_incident_current").read_text()
    assert "var('traffic_snapshot_dag_run_id')" in sql
    assert "silver_seoul_traffic_incident" in sql


def test_history_model_uses_transform_pinned_publishable_manifest_run():
    sql = model_sql("silver_seoul_traffic_incident").read_text(encoding="utf-8")

    assert "var('traffic_snapshot_dag_run_id')" in sql


def test_silver_models_declare_conditional_model_dependencies():
    history_sql = model_sql("silver_seoul_traffic_incident").read_text(encoding="utf-8")
    current_sql = model_sql("silver_seoul_traffic_incident_current").read_text(
        encoding="utf-8"
    )

    assert (
        "-- depends_on: {{ ref('asac_axes', 'seoul_admin_dong_boundary') }}"
        in history_sql
    )
    assert "-- depends_on: {{ ref('silver_seoul_traffic_incident') }}" in current_sql


def test_history_latest_record_contract_uses_the_same_transform_pinned_run():
    sql = singular_sql("assert_silver_traffic_latest_publishable_record.sql").read_text(
        encoding="utf-8"
    )
    compact_sql = " ".join(sql.split())

    assert "var('traffic_snapshot_dag_run_id')" in sql
    assert "requested_run" in sql
    assert "configured_run" in sql
    assert (
        "cast(bronze.dag_run_id as varchar) = configured_run.dag_run_id" in compact_sql
    )
    assert "missing_pinned_run" in sql
    assert "silver_watermark" not in sql


def test_current_snapshot_contract_test_uses_transform_pinned_run():
    sql = singular_sql("assert_traffic_current_pinned_publishable_run.sql").read_text()

    assert "var('traffic_snapshot_dag_run_id')" in sql


def test_current_snapshot_contract_keeps_pinned_correctness_and_grace_freshness_separate():
    sql = (
        singular_sql("assert_traffic_current_pinned_publishable_run.sql")
        .read_text(encoding="utf-8")
        .lower()
    )
    compact_sql = " ".join(sql.split())

    assert "group by cast(dag_run_id as varchar)" in sql
    assert "publishable_rank" in sql
    assert "publishable_rank > 3" in sql
    assert "missing_pinned_run" in sql
    assert "stale_rows" in sql
    assert "missing_rows" in sql
    assert "extra_rows" in sql
    assert "is distinct from pinned_run.dag_run_id" in sql
    assert (
        "select * from expected_current except select * from actual_current"
        in compact_sql
    )
    assert (
        "select * from actual_current except select * from expected_current"
        in compact_sql
    )


def test_current_snapshot_contract_does_not_reanchor_correctness_to_live_latest():
    sql = (
        singular_sql("assert_traffic_current_pinned_publishable_run.sql")
        .read_text(encoding="utf-8")
        .lower()
    )

    assert "var('traffic_snapshot_dag_run_id')" in sql
    assert "limit 1" not in sql


def test_current_snapshot_contract_uses_the_dag_publishable_predicate_without_terminal_rewrite():
    sql = (
        singular_sql("assert_traffic_current_pinned_publishable_run.sql")
        .read_text(encoding="utf-8")
        .lower()
    )
    compact_sql = " ".join(sql.split())

    assert "manifest_event_rank" not in sql
    assert "max(cast(event_at as timestamp(6))) as event_at" in compact_sql
    assert "and status = 'success'" in compact_sql
    assert "and is_publishable" in compact_sql


def test_current_snapshot_contract_allows_continued_zero_incident_runs_inside_freshness_check():
    sql = (
        singular_sql("assert_traffic_current_pinned_publishable_run.sql")
        .read_text(encoding="utf-8")
        .lower()
    )
    compact_sql = " ".join(sql.split())

    assert "newer_valid_bronze" in sql
    assert "exists (select 1 from actual_current)" in compact_sql
    assert "exists (select 1 from newer_valid_bronze)" in compact_sql


def test_gold_summary_reads_current_incidents_not_history():
    sql = model_sql("gold_traffic_incident_summary").read_text()
    assert "silver_seoul_traffic_incident_current" in sql


def test_snapshot_recovery_models_are_isolated_from_current_relations():
    metadata_sql = model_sql("recovery_traffic_snapshot_metadata").read_text(
        encoding="utf-8"
    )
    silver_sql = model_sql("recovery_silver_seoul_traffic_incident").read_text(
        encoding="utf-8"
    )
    gold_sql = model_sql("recovery_gold_traffic_incident_summary").read_text(
        encoding="utf-8"
    )

    assert "ref('recovery_silver_seoul_traffic_incident')" in metadata_sql
    assert "cast(dag_run_id as varchar) as snapshot_dag_run_id" in metadata_sql
    assert "where is_snapshot_marker" in metadata_sql
    assert "var('traffic_snapshot_dag_run_id')" in silver_sql
    assert "snapshot_marker as" in silver_sql
    assert "true as is_snapshot_marker" in silver_sql
    assert "false as is_snapshot_marker" in silver_sql
    assert "source('traffic_bronze', 'seoul_traffic_incident')" in silver_sql
    assert "silver_seoul_traffic_incident_current" not in silver_sql
    assert "ref('recovery_traffic_snapshot_metadata')" in gold_sql
    assert "ref('recovery_silver_seoul_traffic_incident')" in gold_sql
    assert "where not is_snapshot_marker" in gold_sql
    assert "silver_seoul_traffic_incident_current" not in gold_sql


def test_snapshot_recovery_contract_validates_the_requested_publishable_run():
    sql = singular_sql(
        "assert_recovery_silver_traffic_snapshot_matches_bronze.sql"
    ).read_text(encoding="utf-8")
    compact_sql = " ".join(sql.split())

    assert "var('traffic_snapshot_dag_run_id')" in sql
    assert "requested_run" in sql
    assert "configured_run" in sql
    assert "metadata_run" in sql
    assert "missing_pinned_run" in sql
    assert "metadata_run_mismatch" in sql
    assert "silver_marker_run" in sql
    assert "silver_marker_run_mismatch" in sql
    assert "ref('recovery_traffic_snapshot_metadata')" in sql
    assert "ref('recovery_silver_seoul_traffic_incident')" in sql
    assert "target.database" not in sql
    assert "target.schema" not in sql
    assert "where exists (select 1 from configured_run)" in compact_sql
    assert (
        "select * from expected_deduped except select * from actual_current"
        in compact_sql
    )
    assert (
        "select * from actual_current except select * from expected_deduped"
        in compact_sql
    )
    assert "where not is_snapshot_marker" in sql


def test_recovery_singular_tests_resolve_models_through_ref() -> None:
    expected_refs = {
        "assert_recovery_silver_traffic_snapshot_matches_bronze.sql": (
            "recovery_traffic_snapshot_metadata",
            "recovery_silver_seoul_traffic_incident",
        ),
        "assert_recovery_gold_traffic_counts_match_silver.sql": (
            "recovery_traffic_snapshot_metadata",
            "recovery_silver_seoul_traffic_incident",
            "recovery_gold_traffic_incident_summary",
        ),
    }

    for filename, model_names in expected_refs.items():
        sql = singular_sql(filename).read_text(encoding="utf-8")
        for model_name in model_names:
            assert f"ref('{model_name}')" in sql
        assert "target.database" not in sql
        assert "target.schema" not in sql
