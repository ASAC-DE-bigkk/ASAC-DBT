from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from contracts.engine.artifact_io import atomic_write_utf8_text


def test_atomic_write_utf8_text_replaces_destination_without_leaking_temp_files(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "report.json"
    destination.write_text("old", encoding="utf-8")

    atomic_write_utf8_text(destination, '{"message":"서울"}\n')

    assert destination.read_bytes() == f'{{"message":"서울"}}{os.linesep}'.encode(
        "utf-8"
    )
    assert list(tmp_path.glob(f".{destination.name}.*.tmp")) == []


def test_atomic_write_utf8_text_cleans_temp_file_when_replace_fails(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "report.json"
    destination.write_text("keep", encoding="utf-8")

    with patch.object(os, "replace", side_effect=OSError("replace failed")):
        with pytest.raises(OSError, match="replace failed"):
            atomic_write_utf8_text(destination, "new")

    assert destination.read_text(encoding="utf-8") == "keep"
    assert list(tmp_path.glob(f".{destination.name}.*.tmp")) == []
