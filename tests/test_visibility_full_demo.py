"""Tests for ``examples/visibility_full_demo.py`` (M3).

These tests verify the M3 demo is safe-by-default and produces the four
artifacts (transcript.txt, trace.stderr, metrics.json, summary.md) when
driven through a mocked OpenAI-compatible provider.

The ``OpenAIProvider`` import in the demo module is monkeypatched in
every test that does not need a real provider:

  * key-less / no-confirm tests use ``_ExplodingProvider`` (raises if
    instantiated) to prove the safe-by-default path never constructs a
    real provider.
  * artifact-writing tests substitute a ``MockProvider``-backed shim
    that returns scripted tool-calls and a final answer, so the loop
    actually drives ``read_file`` against the workspace, fills
    ``trace.stderr`` with several ``[trace] [budget]`` / ``[trace]
    [externalize]`` lines, and updates ``MetricsCollector`` counters.

All tests redirect the artifact root to ``tmp_path`` via the
``--output-root`` flag so nothing is written inside the repo.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from simple_coding_agent.provider import MockProvider

_EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"
_DEMO_PATH = _EXAMPLES_DIR / "visibility_full_demo.py"
_PROJECT_ROOT = _EXAMPLES_DIR.parent
_GITIGNORE = _PROJECT_ROOT / ".gitignore"


def _load_demo_module() -> Any:
    """Import ``examples/visibility_full_demo.py`` as a module."""
    spec = importlib.util.spec_from_file_location("visibility_full_demo", _DEMO_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["visibility_full_demo"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def demo(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Load the demo module with ``OpenAIProvider`` defaulted to a tripwire."""
    module = _load_demo_module()

    class _ExplodingProvider:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError(
                "OpenAIProvider must not be constructed in this test path"
            )

    monkeypatch.setattr(module, "OpenAIProvider", _ExplodingProvider)
    try:
        yield module
    finally:
        sys.modules.pop("visibility_full_demo", None)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "OPENAI_API_KEY",
        "DASHSCOPE_API_KEY",
        "OPENAI_BASE_URL",
        "SIMPLE_AGENT_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)


def _install_scripted_provider(
    module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> MockProvider:
    """Replace ``OpenAIProvider`` with a MockProvider-backed shim.

    Three scripted turns:
      turn 1 -> read_file(seed.txt) -> final answer
      turn 2 -> read_file(seed.txt) -> final answer
      turn 3 -> final answer (auto-learn cue fires on the user message)
    """
    script = [
        MockProvider.tool_call("read_file", {"path": "seed.txt"}, id="tu_r1"),
        MockProvider.direct_answer("I read seed.txt for the first time."),
        MockProvider.tool_call("read_file", {"path": "seed.txt"}, id="tu_r2"),
        MockProvider.direct_answer("I read seed.txt again."),
        MockProvider.direct_answer("Noted: you prefer Python."),
    ]
    inner = MockProvider(script)

    class _ScriptedOpenAIProvider:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self._inner = inner

        def call(self, *args: object, **kwargs: object) -> Any:
            return self._inner.call(*args, **kwargs)

        def stream_call(self, *args: object, **kwargs: object) -> Any:
            return self._inner.stream_call(*args, **kwargs)

    monkeypatch.setattr(module, "OpenAIProvider", _ScriptedOpenAIProvider)
    return inner


# ---------------------------------------------------------------------------
# (a) missing --confirm-api-call -> exit 2, no provider constructed
# ---------------------------------------------------------------------------


def test_missing_confirm_flag_exits_2_without_constructing_provider(
    demo: Any,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = demo.main(["--output-root", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 2
    assert "--confirm-api-call" in captured.out + captured.err
    # If the tripwire fired the test would already have raised AssertionError.


# ---------------------------------------------------------------------------
# (b) --confirm-api-call set but no API key -> exit 3, no provider constructed
# ---------------------------------------------------------------------------


def test_missing_api_key_exits_3_without_constructing_provider(
    demo: Any,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = demo.main(["--confirm-api-call", "--output-root", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 3
    combined = captured.out + captured.err
    assert "OPENAI_API_KEY" in combined or "DASHSCOPE_API_KEY" in combined


# ---------------------------------------------------------------------------
# (c) full run with mocked provider -> 4 artifacts exist and are non-empty
# ---------------------------------------------------------------------------


def test_full_run_writes_four_non_empty_artifacts(
    demo: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_scripted_provider(demo, monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    rc = demo.main(
        ["--confirm-api-call", "--output-root", str(tmp_path), "--model", "stub"]
    )
    assert rc == 0

    run_dirs = list(tmp_path.glob("visibility-demo-*"))
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    for name in ("transcript.txt", "trace.stderr", "metrics.json", "summary.md"):
        path = run_dir / name
        assert path.exists(), f"missing {name}"
        assert path.stat().st_size > 0, f"empty {name}"

    # metrics.json must be valid JSON with the MetricsCollector field set.
    payload = json.loads((run_dir / "metrics.json").read_text())
    for key in (
        "full_compacts",
        "snip_invocations",
        "microcompact_invocations",
        "reactive_compacts",
        "externalized_bytes",
        "tokens_per_turn",
    ):
        assert key in payload, f"metrics.json missing {key}"
    assert isinstance(payload["tokens_per_turn"], list)


# ---------------------------------------------------------------------------
# (d) trace.stderr contains at least one budget line and one externalize line
# ---------------------------------------------------------------------------


def test_trace_stderr_contains_budget_and_externalize_lines(
    demo: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_scripted_provider(demo, monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    rc = demo.main(
        ["--confirm-api-call", "--output-root", str(tmp_path), "--model", "stub"]
    )
    assert rc == 0

    run_dir = next(tmp_path.glob("visibility-demo-*"))
    trace = (run_dir / "trace.stderr").read_text(encoding="utf-8")

    budget_lines = [
        line for line in trace.splitlines() if line.startswith("[trace] [budget]")
    ]
    externalize_lines = [
        line
        for line in trace.splitlines()
        if line.startswith("[trace] [externalize]")
    ]
    assert budget_lines, "expected at least one [trace] [budget] line"
    assert externalize_lines, "expected at least one [trace] [externalize] line"


# ---------------------------------------------------------------------------
# (e) summary.md is well-formed markdown with one row per channel
# ---------------------------------------------------------------------------


def test_summary_md_lists_every_channel_and_tokens_per_turn(
    demo: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_scripted_provider(demo, monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    rc = demo.main(
        ["--confirm-api-call", "--output-root", str(tmp_path), "--model", "stub"]
    )
    assert rc == 0

    run_dir = next(tmp_path.glob("visibility-demo-*"))
    summary = (run_dir / "summary.md").read_text(encoding="utf-8")

    expected_channels = (
        "budget",
        "compact",
        "reactive",
        "microcompact",
        "snip",
        "externalize",
        "memory_select",
        "claude_md",
        "auto_learn",
    )
    for channel in expected_channels:
        assert f"| {channel} |" in summary, f"missing row for channel {channel!r}"

    # The summary must also report the tokens-per-turn series so reviewers
    # can see budget pressure at a glance.
    assert "tokens" in summary.lower()


# ---------------------------------------------------------------------------
# (f) .gitignore contains examples/_artifacts/
# ---------------------------------------------------------------------------


def test_gitignore_excludes_artifact_directory() -> None:
    text = _GITIGNORE.read_text(encoding="utf-8")
    assert "examples/_artifacts/" in text
