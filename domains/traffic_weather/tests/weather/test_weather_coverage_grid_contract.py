import csv
from pathlib import Path


TRAFFIC_WEATHER_ROOT = Path(__file__).resolve().parents[2]
DBT_GRID_PATH = (
    TRAFFIC_WEATHER_ROOT / "seeds" / "weather" / "weather_coverage_grid.csv"
)
EXPECTED_GRID_COORDINATES = {
    (nx, ny) for nx in range(56, 66) for ny in range(123, 131)
}
EXPECTED_GRID_IDS = {f"kma_{nx}_{ny}" for nx, ny in EXPECTED_GRID_COORDINATES}


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_weather_coverage_grid_seed_is_the_exact_canonical_80_grid_set():
    assert DBT_GRID_PATH.exists(), "80-grid serving seed must be present"

    rows = _rows(DBT_GRID_PATH)
    coordinates = [(int(row["nx"]), int(row["ny"])) for row in rows]

    assert len(rows) == 80
    assert len(set(coordinates)) == 80
    assert set(coordinates) == EXPECTED_GRID_COORDINATES
    assert {row["grid_id"] for row in rows} == EXPECTED_GRID_IDS
    assert {row["coverage_scope"] for row in rows} == {"seoul_bbox"}
