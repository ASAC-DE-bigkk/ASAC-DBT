from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]

W1_MACRO = Path("macros/weather/weather_v2_contract.sql")
W2_MACRO = Path("macros/weather/weather_w2_contract.sql")
W1_OBSERVATION_MODEL = Path(
    "models/weather/special/silver/silver_kma_vilage_fcst_observation.sql"
)
W1_GRID_MODEL = Path("models/weather/special/silver/silver_kma_vilage_fcst_grid.sql")
W1_BRIDGE_MODEL = Path("models/weather/special/w1/bridge_weather_admin_dong_grid.sql")
W1_GRID_RECONCILIATION_TEST = Path(
    "tests/weather/special/assert_weather_grid_selection_reconciles.sql"
)
W1_OBSERVATION_RECONCILIATION_TEST = Path(
    "tests/weather/special/"
    "assert_weather_observation_publishable_and_counts_reconcile.sql"
)
W2_GOLD_MODEL = Path(
    "models/weather/special/gold/gold_weather_forecast_by_admin_dong.sql"
)
W2_GOLD_SCHEMA = W2_GOLD_MODEL.with_suffix(".yml")
W2_LINEAGE_WORKSET_MODEL = Path(
    "models/weather/special/recovery/"
    "weather_w2_observation_recovery_lineage_workset.sql"
)
W2_DATA_TESTS = Path("tests/weather/special")
W2_REPAIR_RECONCILIATION_TEST = (
    W2_DATA_TESTS / "assert_gold_weather_forecast_by_admin_dong_repair_reconciles.sql"
)
W2_REPAIR_WINDOW_EXTRA_TEST = (
    W2_DATA_TESTS
    / "assert_gold_weather_forecast_by_admin_dong_repair_window_no_extra_rows.sql"
)
W2_REPAIR_WINDOW_LINEAGE_TEST = (
    W2_DATA_TESTS
    / "assert_gold_weather_forecast_by_admin_dong_repair_window_lineage.sql"
)
W2_PUBLIC_CONTRACT_DOC = Path(
    "domains/weather/contracts/docs/public-gold-ai-contract-v1.md"
)
WEATHER_OPERATING_DOC = Path("domains/weather/docs/dbt_contracts.md")
BRIDGE_SEED = Path("seeds/weather/weather_admin_dong_grid_bridge_history.csv")
BRIDGE_SEED_CONTRACT = Path("tests/weather/fixtures/weather_w2_seed_contract.yml")

MODEL_NAME = "gold_weather_forecast_by_admin_dong"
BRIDGE_VERSION = "weather_admin_dong_grid_bridge_v1"
CANONICAL_REVISION_DATE = "2025-04-01"
EXPECTED_BRIDGE_V1_COUNT = 427
EXPECTED_CANONICAL_COUNT = 426
EXPECTED_MAPPED_CANONICAL_COUNT = 425
EXPECTED_COLUMNS = [
    "product_row_id",
    "admin_dong_code",
    "forecast_at",
    "category",
    "admin_dong",
    "gu_code",
    "gu",
    "admin_dong_revision_date",
    "bridge_version",
    "nx",
    "ny",
    "source_grid_place_id",
    "issued_at",
    "collected_at",
    "published_at",
    "fcst_value_raw",
    "fcst_value_num",
    "value_representation",
    "value_num",
    "value_lower_bound",
    "value_upper_bound",
    "qualitative_code",
    "forecast_lead_hours",
    "source_id",
    "dag_run_id",
    "raw_object_key",
    "request_id",
]
NAMED_TESTS = {
    "assert_gold_weather_forecast_by_admin_dong_admin_stamp_exact",
    "assert_gold_weather_forecast_by_admin_dong_admin_revision_exact",
    "assert_gold_weather_forecast_by_admin_dong_admin_join_reconciles",
}
DATA_TESTS = NAMED_TESTS | {
    "assert_gold_weather_forecast_by_admin_dong_grain_unique",
    "assert_gold_weather_forecast_by_admin_dong_product_row_id_reproducible",
    "assert_gold_weather_forecast_by_admin_dong_canonical_source_contract",
    "assert_gold_weather_forecast_by_admin_dong_latest_grid_record",
    "assert_gold_weather_forecast_by_admin_dong_bridge_exclusions_reconcile",
    "assert_gold_weather_forecast_by_admin_dong_repair_reconciles",
    "assert_gold_weather_forecast_by_admin_dong_repair_window_no_extra_rows",
    "assert_gold_weather_forecast_by_admin_dong_repair_window_lineage",
    "assert_gold_weather_forecast_by_admin_dong_repair_no_downgrade",
}
CANONICAL_DATA_TESTS = DATA_TESTS - {
    "assert_gold_weather_forecast_by_admin_dong_grain_unique",
    "assert_gold_weather_forecast_by_admin_dong_product_row_id_reproducible",
}


def repo_path(relative_path: Path) -> Path:
    """Resolve one explicit repository-relative test fixture path."""
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError(f"fixture path must be repository-relative: {relative_path}")
    path = REPO_ROOT / relative_path
    assert path.is_file(), f"missing repository fixture: {relative_path.as_posix()}"
    return path


def read(relative_path: Path) -> str:
    return repo_path(relative_path).read_text(encoding="utf-8")


def compact(text: str) -> str:
    return " ".join(text.lower().split())


def model_contract() -> dict:
    schema = yaml.safe_load(read(W2_GOLD_SCHEMA))
    return next(model for model in schema["models"] if model["name"] == MODEL_NAME)
