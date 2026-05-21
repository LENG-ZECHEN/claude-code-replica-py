"""Phase C2 demo tests: ``examples/microcompact_demo.py``.

The demo's job is to drive ``MicroCompactor`` end-to-end so M2's exit-gate
marker appears on stdout. These tests assert the marker — not internal
implementation details — so the demo can evolve without breaking them.

Test plan: RUNTIME_ACTIVATION_PLAN.md section 3.3, milestone M2 exit gate.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

import pytest

_EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"
_DEMO_PATH = _EXAMPLES_DIR / "microcompact_demo.py"


def _load_demo_module() -> Any:
    spec = importlib.util.spec_from_file_location("microcompact_demo", _DEMO_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["microcompact_demo"] = module
    spec.loader.exec_module(module)
    return module


def test_microcompact_demo_returns_zero_and_prints_marker(
    capsys: pytest.CaptureFixture[str],
) -> None:
    demo = _load_demo_module()
    try:
        rc = demo.main([])
    finally:
        sys.modules.pop("microcompact_demo", None)

    captured = capsys.readouterr()

    assert rc == 0
    match = re.search(
        r"microcompact fired \(results cleared=(\d+)\)", captured.out
    )
    assert match is not None, captured.out
    cleared = int(match.group(1))
    assert cleared >= 1


def test_microcompact_demo_does_not_fire_when_recent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """With ``--fresh`` the demo seeds recent timestamps and microcompact skips."""
    demo = _load_demo_module()
    try:
        rc = demo.main(["--fresh"])
    finally:
        sys.modules.pop("microcompact_demo", None)

    captured = capsys.readouterr()

    assert rc == 0
    assert "microcompact skipped" in captured.out
    assert "microcompact fired" not in captured.out


def test_microcompact_demo_reports_aged_timestamp(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The demo prints how stale the seeded assistant message is."""
    demo = _load_demo_module()
    try:
        demo.main([])
    finally:
        sys.modules.pop("microcompact_demo", None)

    captured = capsys.readouterr()
    match = re.search(r"assistant message aged:\s*(\d+)\s*min", captured.out)
    assert match is not None, captured.out
    assert int(match.group(1)) >= 60
