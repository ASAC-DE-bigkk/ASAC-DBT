#!/usr/bin/env python3
"""Compatibility facade for public-Gold catalog comparison."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:  # Support direct execution of this public facade.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from contracts.engine._catalog_contract.cli import main
from contracts.engine._catalog_contract.comparison import compare_public_gold_catalog
from contracts.engine._catalog_contract.reporting import render_json

__all__ = [
    "compare_public_gold_catalog",
    "main",
    "render_json",
]


if __name__ == "__main__":
    raise SystemExit(main())
