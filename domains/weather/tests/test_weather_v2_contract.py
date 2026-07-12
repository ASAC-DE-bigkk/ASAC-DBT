import csv
import hashlib
from pathlib import Path


WEATHER_DIR = Path(__file__).parents[1]
REPO_DIR = WEATHER_DIR.parents[1]


def read(relative_path: str) -> str:
    return (WEATHER_DIR / relative_path).read_text(encoding="utf-8")


def test_signature_uses_tagged_json_array_utf8_sha256_contract():
    sql = read("macros/weather_v2_contract.sql")
    assert "macro weather_kma_item_signature" in sql
    assert "weather_kma_item_v1" in sql
    assert "N:<NULL>" in sql
    assert "V:" in sql
    assert "json_format(cast(array[" in sql
    assert "to_utf8(" in sql
    assert "sha256(" in sql
    assert "lower(to_hex(" in sql
    assert "concat_ws" not in sql
    tagged = sql[sql.index("{%- set tagged") : sql.index("] -%}")]
    positions = [tagged.index(f"~ {field} ~") for field in (
        "base_date", "base_time", "nx", "ny", "category",
        "fcst_date", "fcst_time", "fcst_value",
    )]
    assert positions == sorted(positions)


def test_initial_build_guard_and_lookback_fail_closed():
    sql = read("macros/weather_v2_contract.sql")
    assert "flags.FULL_REFRESH" in sql
    assert "weather_w1_initial_build_mode" in sql
    assert "bounded_isolated_smoke" in sql
    assert "weather_contract_test_" in sql
    assert "weather_w1_lookback_minutes" in sql
    assert "default=30" in sql
    assert "exceptions.raise_compiler_error" in sql


def test_observation_declares_merge_grain_page_and_time_lineage():
    sql = read("models/silver/silver_kma_vilage_fcst_observation.sql")
    assert "materialized='incremental'" in sql
    assert "incremental_strategy='merge'" in sql
    assert "unique_key=['dag_run_id', 'raw_object_key', 'page_no', 'source_item_key']" in sql
    assert "on_schema_change='fail'" in sql
    assert "views_enabled=false" in sql
    assert "on_table_exists='drop'" in sql
    assert "full_refresh=false" in sql
    assert "weather_w1_initial_build_guard()" in sql
    assert "source_page_no" in sql
    assert "missing_legacy" in sql
    assert "source_duplicate_count" in sql
    assert "category_raw" in sql
    assert "bronze_collected_at_utc" in sql
    assert "manifest_event_at_utc" in sql
    assert "asac_axes.utc_to_kst" in sql
    assert "time_parse_state" in sql
    assert ">= (" in sql
    assert "weather_w1_lookback_minutes()" in sql


def test_grid_declares_native_grain_and_exact_winner_order():
    sql = read("models/silver/silver_kma_vilage_fcst_grid.sql")
    assert "materialized='incremental'" in sql
    assert "incremental_strategy='merge'" in sql
    assert "unique_key=['nx', 'ny', 'issued_at', 'forecast_at', 'category']" in sql
    assert "weather_w1_initial_build_guard()" in sql
    assert "full_refresh=false" in sql
    expected_order = (
        "collected_at desc, raw_object_key desc, request_id desc, "
        "dag_run_id desc, page_no desc, source_item_key desc"
    )
    assert expected_order in " ".join(sql.split())
    assert "kma_value_semantics('category', 'fcst_value_raw')" in sql
    assert "selected_dag_run_id" in sql
    assert "selected_source_item_key" in sql
    assert "category_raw" in sql


def test_bridge_stamps_canonical_fields_only_from_common_dimension():
    sql = read("models/silver/bridge_weather_admin_dong_grid.sql")
    assert "ref('asac_axes', 'dim_admin_dong')" in sql
    assert "canonical.admin_dong_code" in sql
    assert "canonical.admin_dong" in sql
    assert "canonical.gu_code" in sql
    assert "canonical.gu" in sql
    assert "canonical.revision_date as admin_dong_revision_date" in sql
    assert "canonical_mapping_state" in sql
    assert "canonical_join_eligible" in sql
    assert "source_admin_code as admin_dong_code" not in sql


def test_bridge_seed_is_exact_427_row_legacy_copy_with_frozen_evidence():
    legacy_path = WEATHER_DIR / "seeds/weather_place_grid_mapping.csv"
    history_path = WEATHER_DIR / "seeds/weather_admin_dong_grid_bridge_history.csv"
    with legacy_path.open(encoding="utf-8", newline="") as handle:
        legacy = list(csv.DictReader(handle))
    with history_path.open(encoding="utf-8", newline="") as handle:
        history = list(csv.DictReader(handle))

    assert len(legacy) == len(history) == 427
    legacy_keys = {
        (row["place_id"], row["source_admin_code"], row["nx"], row["ny"])
        for row in legacy
    }
    history_keys = {
        (row["place_id"], row["source_admin_code"], row["nx"], row["ny"])
        for row in history
    }
    assert history_keys == legacy_keys
    assert len(legacy_keys) == len(history_keys) == 427
    assert all(row["bridge_version"] == "weather_admin_dong_grid_bridge_v1" for row in history)
    assert all(row["legacy_mapping_method"] == "kma_admin_dong_grid_20260325" for row in history)
    assert all(row["mapping_revision_label"] == "kma_admin_dong_grid_20260325" for row in history)
    assert all(row["recorded_at"] == "2026-07-04 12:38:58.000000" for row in history)
    assert all(row["valid_from_at"] == row["valid_to_at"] == "" for row in history)
    assert all(row["temporal_quality"] == "revision_only" for row in history)


def test_protected_compatibility_sql_is_byte_identical_to_gate_a_base():
    expected = {
        "models/silver/silver_kma_vilage_fcst.sql": "7e3f93ad6f81846fbf90bb84dfe1c7f008874f41",
        "models/silver/silver_weather_forecast_by_admin_dong.sql": "776915cf0dc7c08a3b47fd4ea1128eb9a0dcd2aa",
        "models/gold/dim_weather_place.sql": "42f13fc04b38df096c308e07cb636342e13e89c4",
        "models/gold/gold_weather_forecast_by_place.sql": "2549cfe5a0369ea0ac2fcb0bec5b59bae07d93e8",
    }
    for relative_path, expected_blob in expected.items():
        payload = (WEATHER_DIR / relative_path).read_bytes()
        header = f"blob {len(payload)}\0".encode()
        assert hashlib.sha1(header + payload).hexdigest() == expected_blob


def test_required_singular_tests_exist_and_are_nonempty():
    names = {
        "assert_weather_observation_grain_unique.sql",
        "assert_weather_observation_publishable_and_counts_reconcile.sql",
        "assert_weather_invalid_time_observations_accounted.sql",
        "assert_weather_grid_grain_unique.sql",
        "assert_weather_grid_selected_observation_exists.sql",
        "assert_weather_grid_selection_reconciles.sql",
        "assert_weather_bridge_candidate_grain_unique.sql",
        "assert_weather_bridge_canonical_stamp_exact.sql",
        "assert_weather_bridge_validity_non_overlapping.sql",
        "assert_weather_bridge_fanout_reconciles.sql",
        "assert_weather_bridge_legacy_mapping_reconciles.sql",
        "assert_weather_bridge_temporal_evidence.sql",
    }
    test_dir = WEATHER_DIR / "tests"
    for name in names:
        assert (test_dir / name).read_text(encoding="utf-8").strip()
