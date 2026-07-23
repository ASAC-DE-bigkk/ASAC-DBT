from pathlib import Path

from jinja2 import Environment


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = (
    PROJECT_ROOT
    / "models"
    / "traffic"
    / "transform"
    / "gold"
    / "gold_traffic_incident_current_by_admin_dong_hourly.sql"
)
SNAPSHOT_RECONCILIATION_TEST_PATH = (
    PROJECT_ROOT
    / "tests"
    / "traffic"
    / "transform"
    / "gold"
    / "assert_gold_traffic_current_by_admin_dong_hourly_snapshot_reconciles.sql"
)
FLOW_INCIDENT_CARDINALITY_TEST_PATH = (
    PROJECT_ROOT
    / "tests"
    / "traffic"
    / "transform"
    / "gold"
    / "assert_gold_traffic_incident_x_flow_preserves_incidents.sql"
)
FLOW_INCIDENT_MODEL_PATH = (
    PROJECT_ROOT
    / "models"
    / "traffic"
    / "transform"
    / "gold"
    / "gold_traffic_incident_x_flow.sql"
)


def _render_flow_incident_model(flow_run_id: str) -> tuple[str, list[str]]:
    references: list[str] = []

    def ref(model_name: str) -> str:
        references.append(model_name)
        return f"relation__{model_name}"

    rendered = Environment(autoescape=False).from_string(
        FLOW_INCIDENT_MODEL_PATH.read_text(encoding="utf-8")
    ).render(
        config=lambda **_: "",
        ref=ref,
        var=lambda name, default=None: (
            flow_run_id if name == "traffic_flow_snapshot_dag_run_id" else default
        ),
    )
    return rendered, references


def _assert_fragments_are_ordered(text: str, fragments: tuple[str, ...]) -> None:
    positions = [text.index(fragment) for fragment in fragments]
    assert positions == sorted(positions)


def test_canonical_gold_declares_snapshot_and_graph_dependencies():
    assert MODEL_PATH.exists(), f"missing canonical Gold model: {MODEL_PATH}"

    sql = MODEL_PATH.read_text(encoding="utf-8")

    assert "var('traffic_snapshot_dag_run_id')" in sql
    assert "ref('silver_seoul_traffic_incident_current')" in sql
    assert "asac_axes.pinned_dim_admin_dong()" in sql
    assert (
        "latest_manifest_run_state("
        "'traffic_bronze', 'collection_run_manifest', 'seoul_traffic_incident'"
        ")" in sql
    )
    assert "source('traffic_bronze', 'seoul_traffic_incident_request_audit')" in sql
    assert "source('traffic_bronze', 'seoul_traffic_incident')" in sql

    compact_sql = " ".join(sql.lower().split())
    assert "manifest_candidates as" in compact_sql
    assert (
        "where manifest.dag_run_id = configured_run.snapshot_dag_run_id"
        in compact_sql
    )
    assert "manifest_status is distinct from 'success'" in compact_sql
    assert "or not coalesce(is_publishable, false)" in compact_sql


def test_snapshot_reconciliation_independently_derives_state_and_evidence():
    sql = SNAPSHOT_RECONCILIATION_TEST_PATH.read_text(encoding="utf-8").lower()
    compact_sql = " ".join(sql.split())

    for dependency in (
        "ref('silver_seoul_traffic_incident_current')",
        "ref('gold_traffic_incident_current_by_admin_dong_hourly')",
        "asac_axes.pinned_dim_admin_dong()",
        "latest_manifest_run_state('traffic_bronze', 'collection_run_manifest', 'seoul_traffic_incident')",
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

    assert "latest_manifest_state as (" in compact_sql
    assert "where manifest.dag_run_id = configured_run.dag_run_id" in compact_sql
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


def test_flow_gold_incident_cardinality_preserves_incidents():
    sql = FLOW_INCIDENT_CARDINALITY_TEST_PATH.read_text(encoding="utf-8")

    assert "ref('gold_traffic_incident_x_flow')" in sql
    assert "ref('silver_seoul_traffic_incident_current')" in sql
    assert "gold_row_count <> incident_row_count" in sql
    assert "gold_incident_count <> incident_incident_count" in sql


def test_flow_incident_model_avoids_flow_relation_when_snapshot_is_unpinned():
    rendered, references = _render_flow_incident_model("")

    assert "silver_seoul_traffic_flow" not in references
    assert "relation__silver_seoul_traffic_flow" not in rendered
    assert "cast(null as varchar) as link_id" in rendered.lower()
    assert "where false" in rendered.lower()
    assert "'missing_flow'" in rendered


def test_flow_incident_model_reads_the_exact_pinned_flow_relation():
    rendered, references = _render_flow_incident_model("flow-run-42")

    assert "silver_seoul_traffic_flow" in references
    assert "relation__silver_seoul_traffic_flow" in rendered
    assert "flow-run-42" in rendered
