#!/usr/bin/env python3
"""Compatibility facade for public-Gold manifest validation."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:  # Support direct execution of this public facade.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from contracts.engine._manifest_contract.cli import main
from contracts.engine._manifest_contract.foundation import (
    MAX_JSON_CONTAINERS,
    render_json,
)
from contracts.engine._manifest_contract.service import validate_manifest

__all__ = [
    "MAX_JSON_CONTAINERS",
    "main",
    "render_json",
    "validate_manifest",
]


if __name__ == "__main__":
    raise SystemExit(main())
