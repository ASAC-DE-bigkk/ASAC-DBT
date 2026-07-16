#!/usr/bin/env python3
"""citydata 모델 yml ↔ 실제 테이블 컬럼 드리프트 검사 (CI 게이트).

SQL(비즈니스 로직)이 산출하는 실제 컬럼과 레이어별 model yml(문서/컨텍스트) 선언이
어긋나면 실패한다. 문서는 models/ 하위 모든 *.yml 을 읽어 병합한다
(silver/_citydata_silver__models.yml · gold/_citydata_gold__models.yml · sources.yml).
- **yml 누락**: 테이블엔 있는데 yml 에 없는 컬럼 (문서화 안 됨) → FAIL
- **yml 유령**: yml 엔 있는데 테이블엔 없는 컬럼 (오래된 문서) → FAIL
- **설명 없음**: yml 에 있으나 description 없는 컬럼 → 기본 WARN (--strict 면 FAIL)

실제 컬럼은 dev 카탈로그(iceberg_dev.seoul_citydata)의 information_schema 에서 읽는다.
CI 는 dev 빌드 후 이 스크립트를 돌린다.

usage:
  python check_schema_drift.py                # 누락/유령 있으면 exit 1
  python check_schema_drift.py --strict       # 설명 없는 컬럼도 exit 1
  python check_schema_drift.py --schema seoul_citydata --host trino --port 8080
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import trino.dbapi
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MODELS_DIR = os.path.normpath(os.path.join(HERE, "..", "models"))


def load_models(models_dir: str) -> dict:
    """models/ 하위 모든 *.yml 의 models: 를 병합해 {name: model} 로."""
    models: dict = {}
    for path in glob.glob(os.path.join(models_dir, "**", "*.yml"), recursive=True):
        doc = yaml.safe_load(open(path, encoding="utf-8")) or {}
        for m in (doc.get("models") or []):
            models[m["name"]] = m
    return models


def actual_columns(cur, schema: str, table: str) -> list[str]:
    cur.execute(
        "select column_name from iceberg_dev.information_schema.columns "
        f"where table_schema = '{schema}' and table_name = '{table}' order by ordinal_position"
    )
    return [r[0] for r in cur.fetchall()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models-dir", default=DEFAULT_MODELS_DIR)
    ap.add_argument("--schema", default=os.environ.get("SEOUL_CITYDATA_SCHEMA", "seoul_citydata"))
    ap.add_argument("--host", default=os.environ.get("TRINO_HOST", "trino"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("TRINO_PORT", "8080")))
    ap.add_argument("--strict", action="store_true", help="description 없는 컬럼도 실패로 취급")
    args = ap.parse_args()

    models = load_models(args.models_dir)
    cur = trino.dbapi.connect(
        host=args.host, port=args.port, user="drift_check",
        catalog="iceberg_dev", http_scheme="http",
    ).cursor()

    missing_total = ghost_total = undesc_total = 0
    checked = 0
    for name, m in models.items():
        actual = actual_columns(cur, args.schema, name)
        if not actual:
            continue  # 빌드 안 됐거나 다른 스키마 — 검사 대상 아님
        checked += 1
        declared = {c["name"]: c for c in (m.get("columns") or [])}
        missing = [a for a in actual if a not in declared]
        ghost = [d for d in declared if d not in actual]
        undesc = [d for d in declared if not (declared[d] or {}).get("description")]
        if missing:
            print(f"⚠ {name}: yml 누락(문서화 안 됨) {missing}")
        if ghost:
            print(f"⚠ {name}: yml 유령(테이블 없음) {ghost}")
        if undesc and args.strict:
            print(f"· {name}: 설명 없는 컬럼 {undesc}")
        missing_total += len(missing)
        ghost_total += len(ghost)
        undesc_total += len(undesc)

    print(f"\n검사 모델 {checked}개 · yml 누락 {missing_total} · yml 유령 {ghost_total} · 설명 없음 {undesc_total}")
    fail = missing_total or ghost_total or (args.strict and undesc_total)
    if fail:
        print("❌ 드리프트 발견 — 모델 yml 과 실제 컬럼을 맞추세요.")
        return 1
    print("✅ 드리프트 없음.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
