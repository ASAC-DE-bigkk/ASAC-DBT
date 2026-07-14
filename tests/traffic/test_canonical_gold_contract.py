from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = (
    REPO_ROOT
    / "models"
    / "traffic"
    / "transform"
    / "gold"
    / "gold_traffic_incident_current_by_admin_dong_hourly.sql"
)
SNAPSHOT_RECONCILIATION_TEST_PATH = (
    REPO_ROOT
    / "tests"
    / "traffic"
    / "transform"
    / "gold"
    / "assert_gold_traffic_current_by_admin_dong_hourly_snapshot_reconciles.sql"
)


def _assert_fragments_are_ordered(text: str, fragments: tuple[str, ...]) -> None:
    positions = [text.index(fragment) for fragment in fragments]
    assert positions == sorted(positions)


def test_canonical_gold_declares_snapshot_and_graph_dependencies():
    assert MODEL_PATH.exists(), f"missing canonical Gold model: {MODEL_PATH}"

    sql = MODEL_PATH.read_text(encoding="utf-8")

    assert "var('traffic_snapshot_dag_run_id')" in sql
    assert "ref('silver_seoul_traffic_incident_current')" in sql
    assert "ref('asac_axes', 'dim_admin_dong')" in sql
    assert "source('traffic_bronze', 'collection_run_manifest')" in sql
    assert "source('traffic_bronze', 'seoul_traffic_incident_request_audit')" in sql
    assert "source('traffic_bronze', 'seoul_traffic_incident')" in sql

    compact_sql = " ".join(sql.lower().split())
    _assert_fragments_are_ordered(
        compact_sql,
        (
            "manifest_event_at_utc desc nulls last",
            "manifest_status desc nulls last",
            "is_publishable desc nulls last",
            "expected_rows desc nulls last",
            "actual_rows desc nulls last",
            "expected_raw_objects desc nulls last",
            "actual_raw_objects desc nulls last",
            "failure_reason desc nulls last",
            "manifest_dag_run_id desc nulls last",
        ),
    )


def test_snapshot_reconciliation_independently_derives_state_and_evidence():
    sql = SNAPSHOT_RECONCILIATION_TEST_PATH.read_text(encoding="utf-8").lower()
    compact_sql = " ".join(sql.split())

    for dependency in (
        "ref('silver_seoul_traffic_incident_current')",
        "ref('gold_traffic_incident_current_by_admin_dong_hourly')",
        "ref('asac_axes', 'dim_admin_dong')",
        "source('traffic_bronze', 'collection_run_manifest')",
        "source('traffic_bronze', 'seoul_traffic_incident_request_audit')",
        "source('traffic_bronze', 'seoul_traffic_incident')",
    ):
        assert dependency in sql

    ordered_state_predicates = (
        "when manifest_event_count = 0 then 'missing'",
        "when latest_manifest_event_count <> 1 then 'partial'",
        "when clear_api_failure_count > 0 then 'api_failure'",
        "when terminal_non_api_failure_count > 0 then 'partial'",
        "when audit_request_count = 0 then 'missing'",
        "when parity_failure_count > 0 then 'partial'",
        "when current_mismatch_count > 0 then 'current_mismatch'",
        "when canonical_failure_count > 0 or unmapped_incident_count > 0 then 'spatial_mapping_incomplete'",
        "when expected_incident_count = 0 then 'complete_zero'",
        "else 'complete'",
    )
    _assert_fragments_are_ordered(compact_sql, ordered_state_predicates)

    assert "httpproblemerror in land_seoul_traffic_raw" in compact_sql
    assert "parseerror in land_seoul_traffic_raw" in compact_sql
    assert "runtimeerror in land_seoul_traffic_raw" not in compact_sql
    assert "nullif(trim(coalesce(failure_reason, '')), '') is not null" in compact_sql

    assert "row_number() over (" in compact_sql
    assert "event_at desc nulls last" in compact_sql
    assert "status desc nulls last" in compact_sql
    assert "is_publishable desc nulls last" in compact_sql
    _assert_fragments_are_ordered(
        compact_sql,
        (
            "event_at desc nulls last",
            "status desc nulls last",
            "is_publishable desc nulls last",
            "expected_rows desc nulls last",
            "actual_rows desc nulls last",
            "expected_raw_objects desc nulls last",
            "actual_raw_objects desc nulls last",
            "failure_reason desc nulls last",
            "dag_run_id desc nulls last",
        ),
    )
    assert (
        "max(case when manifest_row_num = 1 then latest_event_tie_count end)"
        in compact_sql
    )
    assert (
        "max(case when manifest_row_num = 1 then expected_rows end) "
        "as expected_incident_count"
    ) in compact_sql
    assert "case when count(*) = 1 then max(expected_rows)" not in compact_sql
    assert "actual_rows is distinct from expected_incident_count" in compact_sql

    for audit_metadata_column in (
        "request_params_json",
        "payload_hash",
        "result_msg",
        "load_date",
        "dag_run_id",
    ):
        assert f"audit.{audit_metadata_column}" in compact_sql
        assert f"or {audit_metadata_column} is null" in compact_sql
    assert "or start_index <= 0" in compact_sql
    assert "as audit_duplicate_page_count" in compact_sql
    assert "or audit_duplicate_page_count > 0" in compact_sql

    assert "expected_snapshot_as_of_at" in sql
    assert "with_timezone(max(collected_at), 'utc')" in compact_sql
    assert "then audit_snapshot_as_of_at" in compact_sql
    assert "with_timezone(manifest_event_at, 'utc')" in compact_sql
    assert "as manifest_event_at_kst" in compact_sql
    assert "from deduped_current as current" in compact_sql
    assert (
        "gold.status_observed_at is distinct from "
        "coalesce(expected.manifest_event_at_kst, gold.published_at)"
    ) in compact_sql
    assert (
        "gold.hour_at is distinct from "
        "cast(date_trunc('hour', gold.status_observed_at) as timestamp(6))"
    ) in compact_sql
    assert "count(distinct published_at) as published_at_value_count" in compact_sql
    assert "count(distinct hour_at) as hour_at_value_count" in compact_sql
    for evidence_column in (
        "expected_incident_count",
        "audited_row_count",
        "max_page_end_index",
        "unmapped_incident_count",
    ):
        assert (
            f"gold.{evidence_column} is distinct from expected.{evidence_column}"
            in compact_sql
        )


def test_snapshot_reconciliation_keeps_one_current_evidence_row_when_current_is_empty():
    sql = SNAPSHOT_RECONCILIATION_TEST_PATH.read_text(encoding="utf-8").lower()
    current_evidence_sql = sql.split("current_evidence as (", maxsplit=1)[1].split(
        "\n),\n\ncanonical as (", maxsplit=1
    )[0]

    assert "count_if(" in current_evidence_sql
    assert "from current_rows" in current_evidence_sql
    assert "cross join configured_run" in current_evidence_sql
    assert "group by" not in current_evidence_sql
    assert "count_if(current_rows.source_record_id is null)" in current_evidence_sql
    assert (
        "count_if(current_rows.dag_run_id is distinct from configured_run.dag_run_id)"
        in current_evidence_sql
    )
    assert (
        "count_if(current_rows.source_id is distinct from configured_run.source_id)"
        in current_evidence_sql
    )
