from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
HELPER_PATH = REPO_ROOT / "contracts" / "engine" / "tests" / "capabilities.py"


def _load_helper():
    assert HELPER_PATH.is_file(), f"shared capability helper is missing: {HELPER_PATH}"
    spec = importlib.util.spec_from_file_location(
        "contract_test_capabilities", HELPER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_symlink_probe_treats_expected_os_errors_as_unavailable() -> None:
    helper = _load_helper()

    def denied(_target: Path, _link: Path) -> None:
        raise OSError("symlink privilege is unavailable")

    assert helper._probe_symlink_capability(denied) is False


def test_symlink_probe_reports_success_when_creation_is_allowed() -> None:
    helper = _load_helper()

    assert helper._probe_symlink_capability(lambda _target, _link: None) is True


def test_symlink_guard_is_a_unittest_skip_decorator() -> None:
    helper = _load_helper()

    def sample_test() -> None:
        return None

    guarded = helper.requires_symlink_capability(sample_test)
    assert hasattr(guarded, "__unittest_skip__")
    assert isinstance(guarded.__unittest_skip__, bool)
