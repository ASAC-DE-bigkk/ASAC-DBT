"""weather 매핑 seed 의 grid_distance_m 백필 (#511).

행정동 중심좌표(seed 의 latitude/longitude)와 그 행에 배정된 KMA 격자(nx/ny)의
셀 중심 사이 거리를 계산해, 스키마에만 있고 전량 공란이던 grid_distance_m 를 채운다.
매핑 신뢰도 지표 — 값이 크면(격자 반셀 ~2.8km 초과) 배정 재검토 신호.

- 격자 중심 좌표: KMA DFS(Lambert Conformal Conic) 역변환 — 기상청 단기예보
  안내서의 표준 상수(Re=6371.00877km, grid=5km, slat 30/60, 원점 126E/38N, xo=43, yo=136).
- 거리: haversine(m), 정수 반올림.
- nx/ny 자체는 절대 바꾸지 않는다(매핑 정본은 kma_admin_dong_grid_20260325 스냅샷).
  대신 좌표→격자 순변환과 대조해 불일치를 보고만 한다.

실행(레포 루트 기준):
  python contracts/weather/scripts/backfill_grid_distance.py
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

# ── KMA DFS 상수 (기상청 단기예보 오픈API 안내서) ──────────────────────────
RE = 6371.00877     # 지구 반경(km)
GRID = 5.0          # 격자 간격(km)
SLAT1 = 30.0        # 표준 위도 1
SLAT2 = 60.0        # 표준 위도 2
OLON = 126.0        # 기준점 경도
OLAT = 38.0         # 기준점 위도
XO = 43             # 기준점 X 좌표(격자)
YO = 136            # 기준점 Y 좌표(격자)

_DEGRAD = math.pi / 180.0
_re = RE / GRID
_slat1 = SLAT1 * _DEGRAD
_slat2 = SLAT2 * _DEGRAD
_olon = OLON * _DEGRAD
_olat = OLAT * _DEGRAD
_sn = math.log(math.cos(_slat1) / math.cos(_slat2)) / math.log(
    math.tan(math.pi * 0.25 + _slat2 * 0.5) / math.tan(math.pi * 0.25 + _slat1 * 0.5)
)
_sf = (math.tan(math.pi * 0.25 + _slat1 * 0.5) ** _sn) * math.cos(_slat1) / _sn
_ro = _re * _sf / (math.tan(math.pi * 0.25 + _olat * 0.5) ** _sn)


def latlon_to_grid(lat: float, lon: float) -> tuple[int, int]:
    ra = _re * _sf / (math.tan(math.pi * 0.25 + lat * _DEGRAD * 0.5) ** _sn)
    theta = lon * _DEGRAD - _olon
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= _sn
    return (
        int(ra * math.sin(theta) + XO + 0.5),
        int(_ro - ra * math.cos(theta) + YO + 0.5),
    )


def grid_to_latlon(nx: int, ny: int) -> tuple[float, float]:
    xn = nx - XO
    yn = _ro - (ny - YO)
    ra = math.sqrt(xn * xn + yn * yn)
    if _sn < 0.0:
        ra = -ra
    alat = 2.0 * math.atan((_re * _sf / ra) ** (1.0 / _sn)) - math.pi * 0.5
    if abs(xn) <= 0.0:
        theta = 0.0
    elif abs(yn) <= 0.0:
        theta = math.pi * 0.5 * (1.0 if xn > 0 else -1.0)
    else:
        theta = math.atan2(xn, yn)
    alon = theta / _sn + _olon
    return (alat / _DEGRAD, alon / _DEGRAD)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def backfill(path: Path) -> tuple[int, int, float]:
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
    assert rows and "grid_distance_m" in rows[0], f"{path}: grid_distance_m 컬럼 없음"
    filled, mismatched, max_d = 0, 0, 0.0
    for row in rows:
        lat, lon = float(row["latitude"]), float(row["longitude"])
        nx, ny = int(row["nx"]), int(row["ny"])
        glat, glon = grid_to_latlon(nx, ny)
        d = round(haversine_m(lat, lon, glat, glon))
        row["grid_distance_m"] = str(d)
        filled += 1
        max_d = max(max_d, d)
        if latlon_to_grid(lat, lon) != (nx, ny):
            mismatched += 1
            print(f"  ⚠ 순변환 불일치(보고만): {path.name} {row.get('place_id') or row.get('source_admin_code')} "
                  f"seed=({nx},{ny}) recomputed={latlon_to_grid(lat, lon)}")
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return filled, mismatched, max_d


def main() -> None:
    # 대상은 현행 매핑 seed 하나뿐이다. weather_admin_dong_grid_bridge_history 는
    # W1 append-only 단언 기록 + 환경 가드(weather_w1_candidate_environment_guard)
    # 대상이라 소급 수정하지 않는다(#511 — 신뢰도 지표는 현행 매핑에서 노출).
    base = Path(__file__).resolve().parents[3] / "seeds" / "weather"
    for name in ("weather_place_grid_mapping.csv",):
        filled, mismatched, max_d = backfill(base / name)
        print(f"{name}: filled={filled} mismatched={mismatched} max_distance_m={max_d:.0f}")


if __name__ == "__main__":
    main()
