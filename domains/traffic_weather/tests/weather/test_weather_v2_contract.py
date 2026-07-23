import csv
import hashlib
import json
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[2]
WEATHER_MODELS = REPO_DIR / "models" / "weather"
WEATHER_MACROS = REPO_DIR / "macros" / "weather"
WEATHER_SEEDS = REPO_DIR / "seeds" / "weather"
WEATHER_TESTS = Path(__file__).resolve().parent


def weather_path(relative_path: str) -> Path:
    relative = Path(relative_path)
    if relative_path == "dbt_project.yml":
        return REPO_DIR / relative
    roots = {
        "macros": WEATHER_MACROS,
        "models": WEATHER_MODELS,
        "seeds": WEATHER_SEEDS,
        "tests": WEATHER_TESTS,
    }
    root = roots[relative.parts[0]]
    matches = list(root.rglob(relative.name))
    assert len(matches) == 1, (
        f"expected one moved Weather path for {relative_path}: {matches}"
    )
    return matches[0]


def read(relative_path: str) -> str:
    return weather_path(relative_path).read_text(encoding="utf-8")


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
    positions = [
        tagged.index(f"~ {field} ~")
        for field in (
            "base_date",
            "base_time",
            "nx",
            "ny",
            "category",
            "fcst_date",
            "fcst_time",
            "fcst_value",
        )
    ]
    assert positions == sorted(positions)


def test_initial_build_guard_and_lookback_fail_closed():
    sql = read("macros/weather_v2_contract.sql")
    schema_helper = read("macros/weather_schema.sql")
    assert "flags.FULL_REFRESH" in sql
    assert "weather_w1_initial_build_mode" in sql
    assert "bounded_isolated_smoke" in sql
    assert "weather_contract_test_" in sql
    assert "weather_w1_lookback_minutes" in sql
    assert "default=30" in sql
    assert "exceptions.raise_compiler_error" in sql
    assert "weather_schema_name()" in sql
    assert "env_var('WEATHER_SCHEMA', 'weather')" in schema_helper
    assert "target.schema" not in sql


def test_observation_declares_merge_grain_page_and_time_lineage():
    sql = read("models/silver/silver_kma_vilage_fcst_observation.sql")
    assert "materialized='incremental'" in sql
    assert "incremental_strategy='merge'" in sql
    assert (
        "unique_key=['dag_run_id', 'raw_object_key', 'page_no', 'source_item_key']"
        in sql
    )
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


def test_bridge_seed_preserves_427_row_legacy_copy_plus_yongsin_backfill():
    legacy_path = weather_path("seeds/weather_place_grid_mapping.csv")
    history_path = weather_path("seeds/weather_admin_dong_grid_bridge_history.csv")
    with legacy_path.open(encoding="utf-8", newline="") as handle:
        legacy = list(csv.DictReader(handle))
    with history_path.open(encoding="utf-8", newline="") as handle:
        history = list(csv.DictReader(handle))

    assert len(legacy) == 427
    assert len(history) == 428
    legacy_keys = {
        (row["place_id"], row["source_admin_code"], row["nx"], row["ny"])
        for row in legacy
    }
    history_keys = {
        (row["place_id"], row["source_admin_code"], row["nx"], row["ny"])
        for row in history
    }
    yongsin_key = ("seoul_admd_1123053600", "1123053600", "61", "127")
    assert history_keys - legacy_keys == {yongsin_key}
    assert legacy_keys <= history_keys
    assert len(legacy_keys) == 427
    assert len(history_keys) == 428
    assert all(
        row["bridge_version"] == "weather_admin_dong_grid_bridge_v1" for row in history
    )
    legacy_copy = [row for row in history if row["place_id"] != "seoul_admd_1123053600"]
    assert all(
        row["legacy_mapping_method"] == "kma_admin_dong_grid_20260325"
        for row in legacy_copy
    )
    assert all(
        row["mapping_revision_label"] == "kma_admin_dong_grid_20260325"
        for row in legacy_copy
    )
    assert all(
        row["recorded_at"] == "2026-07-04 12:38:58.000000" for row in legacy_copy
    )
    yongsin = next(
        row for row in history if row["place_id"] == "seoul_admd_1123053600"
    )
    assert yongsin["legacy_mapping_method"] == ""
    assert yongsin["mapping_revision_label"] == "manual_yongsin_backfill_20260723"
    assert yongsin["mapping_method"] == "manual_centroid_backfill"
    assert yongsin["recorded_at"] == "2026-07-23 12:00:00.000000"
    assert all(row["valid_from_at"] == row["valid_to_at"] == "" for row in history)
    assert all(row["temporal_quality"] == "revision_only" for row in history)


def test_compatibility_sql_changes_only_for_issue_140_replay_window():
    expected = {
        "models/gold/dim_weather_place.sql": "42f13fc04b38df096c308e07cb636342e13e89c4",
        "models/gold/gold_weather_forecast_by_place.sql": "2549cfe5a0369ea0ac2fcb0bec5b59bae07d93e8",
    }
    for relative_path, expected_blob in expected.items():
        # Normalize only a Windows CRLF checkout before comparing this source
        # content with the LF-normalized Gate A blob.
        payload = weather_path(relative_path).read_bytes().replace(b"\r\n", b"\n")
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
        "assert_weather_grid_exclusions_accounted.sql",
        "assert_weather_item_signature_known_vectors.sql",
        "assert_weather_bridge_candidate_grain_unique.sql",
        "assert_weather_bridge_canonical_stamp_exact.sql",
        "assert_weather_bridge_validity_non_overlapping.sql",
        "assert_weather_bridge_fanout_reconciles.sql",
        "assert_weather_bridge_legacy_mapping_reconciles.sql",
        "assert_weather_bridge_temporal_evidence.sql",
    }
    for name in names:
        assert weather_path(f"tests/{name}").read_text(encoding="utf-8").strip()


def test_observation_exposes_grid_exclusion_states_and_reconciliation_test():
    observation = read("models/silver/silver_kma_vilage_fcst_observation.sql")
    assert "as grid_coordinate_state" in observation
    assert "as grid_category_state" in observation
    assert "as grid_time_state" in observation
    assert "as grid_eligibility_state" in observation
    assert "'eligible'" in observation
    assert "'excluded'" in observation

    reconciliation = read("tests/assert_weather_grid_exclusions_accounted.sql")
    assert "grid_coordinate_state" in reconciliation
    assert "grid_category_state" in reconciliation
    assert "grid_time_state" in reconciliation
    assert "grid_eligibility_state" in reconciliation
    assert "excluded_in_grid" in reconciliation


def test_item_signature_known_vector_data_test_is_independent():
    vector_test = read("tests/assert_weather_item_signature_known_vectors.sql")
    expected = {
        "4d7ae418621bf4bb7ecb7e551b7b626a8415d161362baab661ebb424c45dc197": [
            "V:20260712",
            "V:0500",
            "V:60",
            "V:127",
            "V:TMP",
            "V:20260712",
            "V:0600",
            "V:1.5",
        ],
        "129834ce8c6e874985eee88f256855ddde25b8c45bc498a8414aaf063baa2c9f": [
            "N:<NULL>",
            "N:<NULL>",
            "N:<NULL>",
            "N:<NULL>",
            "N:<NULL>",
            "N:<NULL>",
            "N:<NULL>",
            "N:<NULL>",
        ],
    }
    for expected_hash, vector in expected.items():
        payload = json.dumps(vector, ensure_ascii=False, separators=(",", ":")).encode()
        assert hashlib.sha256(payload).hexdigest() == expected_hash
        assert expected_hash in vector_test
    assert "weather_kma_item_signature(" in vector_test
    normalized = " ".join(vector_test.split())
    assert "where actual_hash is distinct from expected_hash" in normalized
    assert "where actual_hash <> expected_hash" not in normalized


def test_bridge_and_seed_require_isolated_candidate_runtime_guard():
    macros = read("macros/weather_v2_contract.sql")
    bridge = read("models/silver/bridge_weather_admin_dong_grid.sql")
    project = read("dbt_project.yml")
    assert "macro weather_w1_candidate_environment_guard" in macros
    assert "macro weather_w1_candidate_seed_guard" in macros
    candidate_guard = macros[
        macros.index("macro weather_w1_candidate_environment_guard") : macros.index(
            "macro weather_w1_candidate_seed_guard"
        )
    ]
    assert "flags.FULL_REFRESH" in candidate_guard
    assert (
        "weather_w1_candidate_environment_guard('bridge_weather_admin_dong_grid')"
        in bridge
    )
    assert '+pre-hook: "{{ weather_w1_candidate_seed_guard() }}"' in project
