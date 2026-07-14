"""Deterministic byte delivery helpers for contract CLI artifacts."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import TextIO


def atomic_write_utf8_text(path: Path, value: str) -> None:
    """Atomically replace *path* with UTF-8 text and clean failed temp files."""
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def write_utf8_stdout(value: str, *, stream: TextIO | None = None) -> None:
    """Write text as UTF-8 bytes, independent of stdout's configured encoding."""
    target = sys.stdout if stream is None else stream
    binary_stream = getattr(target, "buffer", None)
    if binary_stream is not None:
        binary_stream.write(value.encode("utf-8"))
        binary_stream.flush()
        return
    target.write(value)
    target.flush()
