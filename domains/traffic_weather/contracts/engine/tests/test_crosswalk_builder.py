import csv
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
BUILDER = REPOSITORY_ROOT / "packages" / "asac_axes" / "scripts" / "build_crosswalk.py"
OUTPUT_NAMES = {
    "seoul_admin_dong_boundary.csv",
    "seoul_admin_dong_crosswalk.csv",
    "seoul_gu_boundary.csv",
}


def _write_csv(path: Path, header: list[str], row: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerow(row)


def _fixture_inputs(root: Path) -> dict[str, Path]:
    inputs = {
        "weather_grid": root / "weather.csv",
        "dong_boundary": root / "dong.csv",
        "gu_boundary": root / "gu.csv",
    }
    _write_csv(
        inputs["weather_grid"],
        [
            "place_id",
            "place_name",
            "gu",
            "admin_dong",
            "latitude",
            "longitude",
            "mapping_method",
            "source_admin_code",
        ],
        [
            "seoul_admd_2222200000",
            "Fixture place",
            "Mapo-gu",
            "Mapo-dong",
            "37.1",
            "127.1",
            "fixture-snapshot",
            "2222200000",
        ],
    )
    _write_csv(
        inputs["dong_boundary"],
        ["sigungu", "sigungu_code", "dong", "dong_code", "boundary_wkt"],
        ["Mapo-gu", "33333", "Mapo-dong", "3333300", "DONG_WKT"],
    )
    _write_csv(
        inputs["gu_boundary"],
        ["sigungu", "sigungu_eng", "sigungu_code", "boundary_wkt"],
        ["Mapo-gu", "Mapo-gu", "33333", "GU_WKT"],
    )
    return inputs


def _run_builder(inputs: dict[str, Path], output_dir: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(BUILDER),
            "--weather-grid",
            str(inputs["weather_grid"]),
            "--dong-boundary",
            str(inputs["dong_boundary"]),
            "--gu-boundary",
            str(inputs["gu_boundary"]),
            "--output-dir",
            str(output_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _read_single_row(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1
    return rows[0]


def test_crosswalk_cli_combines_each_injected_source(tmp_path: Path) -> None:
    inputs = _fixture_inputs(tmp_path)
    output_dir = tmp_path / "output"

    _run_builder(inputs, output_dir)

    assert {path.name for path in output_dir.iterdir()} == OUTPUT_NAMES
    assert _read_single_row(output_dir / "seoul_admin_dong_crosswalk.csv") == {
        "admin_dong_code": "2222200000",
        "gu_code": "22222",
        "stat_dong_code": "3333300",
        "stat_gu_code": "33333",
        "gu": "Mapo-gu",
        "admin_dong": "Mapo-dong",
        "latitude": "37.1",
        "longitude": "127.1",
        "snapshot_ref": "fixture-snapshot",
    }
    assert _read_single_row(output_dir / "seoul_admin_dong_boundary.csv") == {
        "sigungu": "Mapo-gu",
        "sigungu_code": "33333",
        "dong": "Mapo-dong",
        "dong_code": "3333300",
        "boundary_wkt": "DONG_WKT",
        "admin_dong_code": "2222200000",
        "gu_code": "22222",
    }
    assert _read_single_row(output_dir / "seoul_gu_boundary.csv") == {
        "sigungu": "Mapo-gu",
        "sigungu_eng": "Mapo-gu",
        "sigungu_code": "33333",
        "boundary_wkt": "GU_WKT",
        "gu_code": "22222",
    }


def test_crosswalk_cli_emits_identical_bytes_on_repeated_runs(tmp_path: Path) -> None:
    inputs = _fixture_inputs(tmp_path)
    first_output = tmp_path / "first"
    second_output = tmp_path / "second"

    _run_builder(inputs, first_output)
    _run_builder(inputs, second_output)

    assert {name: (first_output / name).read_bytes() for name in OUTPUT_NAMES} == {
        name: (second_output / name).read_bytes() for name in OUTPUT_NAMES
    }
