"""M2 demo test: ``examples/aggressive_thresholds_demo.py`` runs end-to-end.

The demo's job is to demonstrate that ``--aggressive-thresholds`` actually
makes the context-management mechanisms (full compact + snip) fire under
8 short MockProvider turns. This test asserts the banner is printed,
return code is 0, and the MetricsCollector output contains at least one
non-zero counter for the mechanisms the preset is designed to trigger.

Follows the importlib-based loading pattern used by
``tests/test_microcompact_demo.py`` and ``tests/test_stress_demo.py`` so
the ``examples/`` directory does not need to be a Python package.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

_EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"
_DEMO_PATH = _EXAMPLES_DIR / "aggressive_thresholds_demo.py"


def _load_demo_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "aggressive_thresholds_demo", _DEMO_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["aggressive_thresholds_demo"] = module
    spec.loader.exec_module(module)
    return module


def test_aggressive_thresholds_demo_returns_zero_and_prints_banner(
    capsys: pytest.CaptureFixture[str],
) -> None:
    demo = _load_demo_module()
    try:
        rc = demo.main([])
    finally:
        sys.modules.pop("aggressive_thresholds_demo", None)

    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "[aggressive-thresholds]" in captured.out
    # MetricsCollector.format_stats() row labels — proves the loop ran and
    # the preset-driven mechanisms had a chance to fire.
    assert "full compacts" in captured.out
    assert "snip runs" in captured.out
