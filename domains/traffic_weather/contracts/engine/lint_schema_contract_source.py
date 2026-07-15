#!/usr/bin/env python3
"""Compatibility facade for source schema contract linting."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:  # Support direct execution of this public facade.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from contracts.engine._schema_contract.cli import main
from contracts.engine._schema_contract.reporting import render_report
from contracts.engine._schema_contract.service import lint_schema_contracts
from contracts.engine._schema_contract.types import (
    MAX_FILE_BYTES,
    MAX_LINE_COUNT,
    MAX_LINE_LENGTH,
    MAX_NESTING_DEPTH,
    MAX_SCALAR_LENGTH,
)

__all__ = [
    "MAX_FILE_BYTES",
    "MAX_LINE_COUNT",
    "MAX_LINE_LENGTH",
    "MAX_NESTING_DEPTH",
    "MAX_SCALAR_LENGTH",
    "lint_schema_contracts",
    "main",
    "render_report",
]


if __name__ == "__main__":
    raise SystemExit(main())
