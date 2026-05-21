"""Phase C1 demo tests: ``examples/stress_demo.py``.

The demo's job is to drive the unit-tested context-management mechanisms
(full-compact, reactive-compact) end-to-end so M2's exit-gate markers
appear on stdout. These tests assert the markers — not implementation
details — so the demo can evolve without breaking them.

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
_DEMO_PATH = _EXAMPLES_DIR / "stress_demo.py"


def _load_demo_module() -> Any:
    """Import ``examples/stress_demo.py`` as a module for testing."""
    spec = importlib.util.spec_from_file_location("stress_demo", _DEMO_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["stress_demo"] = module
    spec.loader.exec_module(module)
    return module


def test_stress_demo_returns_zero_and_prints_compact_marker(
    capsys: pytest.CaptureFixture[str],
) -> None:
    demo = _load_demo_module()
    try:
        rc = demo.main([])
    finally:
        sys.modules.pop("stress_demo", None)

    captured = capsys.readouterr()

    assert rc == 0
    match = re.search(
        r"compact fired \(messages_summarized=(\d+)\)", captured.out
    )
    assert match is not None, captured.out
    assert int(match.group(1)) >= 1


def test_stress_demo_prints_reactive_compact_marker(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The demo must also exercise the PromptTooLong -> reactive compact path."""
    demo = _load_demo_module()
    try:
        demo.main([])
    finally:
        sys.modules.pop("stress_demo", None)

    captured = capsys.readouterr()

    assert "reactive compact fired" in captured.out


def test_stress_demo_reports_total_conversation_size_at_least_200k(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """RUNTIME_ACTIVATION_PLAN.md C1 calls for a 200k+ char conversation."""
    demo = _load_demo_module()
    try:
        demo.main([])
    finally:
        sys.modules.pop("stress_demo", None)

    captured = capsys.readouterr()
    match = re.search(r"total conversation size:\s*(\d[\d,]*)\s*chars", captured.out)
    assert match is not None, captured.out
    size = int(match.group(1).replace(",", ""))
    assert size >= 200_000
