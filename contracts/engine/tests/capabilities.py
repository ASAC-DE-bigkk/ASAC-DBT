from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Callable


SYMLINK_SKIP_REASON = "symlink creation is unavailable on this test host"
SymlinkCreator = Callable[[Path, Path], None]


def _create_symlink(target: Path, link: Path) -> None:
    link.symlink_to(target)


def _probe_symlink_capability(create_symlink: SymlinkCreator) -> bool:
    with tempfile.TemporaryDirectory(prefix="public-gold-symlink-probe-") as temp_dir:
        root = Path(temp_dir)
        target = root / "target.txt"
        link = root / "target-link.txt"
        target.write_text("probe", encoding="utf-8")
        try:
            create_symlink(target, link)
        except (NotImplementedError, OSError):
            return False
        return True


def symlink_capability_available() -> bool:
    return _probe_symlink_capability(_create_symlink)


requires_symlink_capability = unittest.skipUnless(
    symlink_capability_available(),
    SYMLINK_SKIP_REASON,
)
