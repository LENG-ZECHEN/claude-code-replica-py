"""Tests for `_set_permission_mode` metric dispatch + idempotency.

Follow-up fixes to plan-surface (Items 1 + 3 from the post-archive review-time
deferred ledger):

- Item 1: slash-toggle exits and tool-approved exits used to both bump
  `plan_mode_exits_approved`. Now slash bumps `plan_mode_exits_manual` and
  tool bumps `plan_mode_exits_approved`.
- Item 3: `_set_permission_mode` is now idempotent — calling it with the
  current mode does NOT bump `plan_mode_entries` or any exit counter and
  does NOT emit a permission trace.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import simple_coding_agent.claude_md as cm
from simple_coding_agent.coding_tools import ShellMode
from simple_coding_agent.context import ContextBudget, ContextBuilder
from simple_coding_agent.loop import AgentLoop
from simple_coding_agent.metrics import MetricsCollector
from simple_coding_agent.permission import PermissionMode
from simple_coding_agent.provider import MockProvider
from simple_coding_agent.tool_registry_factory import build_default_registry
from simple_coding_agent.tools import ToolExecutor
from simple_coding_agent.transcript import Transcript


@pytest.fixture(autouse=True)
def _isolate_user_claude_md(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")


def _make_loop(tmp_path: Path) -> AgentLoop:
    transcript = Transcript()
    registry = build_default_registry(tmp_path, shell_mode=ShellMode.MOCK, transcript=transcript)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=8_192)
    return AgentLoop(
        provider=MockProvider([MockProvider.direct_answer("ok")]),
        tool_executor=ToolExecutor(registry),
        transcript=transcript,
        context_builder=ContextBuilder(budget=budget),
        budget=budget,
        registry=registry,
        metrics=MetricsCollector(),
    )


# ---------------------------------------------------------------------------
# Item 1: source-dispatched exit counters
# ---------------------------------------------------------------------------

def test_slash_exit_bumps_manual_not_approved(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    loop._set_permission_mode(PermissionMode.PLAN, source="slash")
    loop._set_permission_mode(PermissionMode.NORMAL, source="slash")
    assert loop._metrics.plan_mode_exits_manual == 1
    assert loop._metrics.plan_mode_exits_approved == 0
    assert loop._metrics.plan_mode_exits_rejected == 0


def test_tool_approved_exit_bumps_approved_not_manual(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    loop._set_permission_mode(PermissionMode.PLAN, source="tool")
    # default source for tool-driven transitions is "tool"; mode_setter calls
    # this with the default kwarg when exit_plan_mode's approval branch runs.
    loop._set_permission_mode(PermissionMode.NORMAL)
    assert loop._metrics.plan_mode_exits_approved == 1
    assert loop._metrics.plan_mode_exits_manual == 0
    assert loop._metrics.plan_mode_exits_rejected == 0


def test_plan_mode_exits_property_sums_all_three(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    loop._metrics.plan_mode_exits_approved = 2
    loop._metrics.plan_mode_exits_rejected = 3
    loop._metrics.plan_mode_exits_manual = 5
    assert loop._metrics.plan_mode_exits == 10


def test_record_plan_mode_exit_manual_method_exists() -> None:
    metrics = MetricsCollector()
    metrics.record_plan_mode_exit_manual()
    metrics.record_plan_mode_exit_manual()
    assert metrics.plan_mode_exits_manual == 2
    assert metrics.plan_mode_exits_approved == 0
    assert metrics.plan_mode_exits_rejected == 0


# ---------------------------------------------------------------------------
# Item 3: idempotent _set_permission_mode
# ---------------------------------------------------------------------------

def test_set_permission_mode_idempotent_on_entry(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    loop._set_permission_mode(PermissionMode.PLAN)
    assert loop._metrics.plan_mode_entries == 1
    # Re-entering PLAN while already in PLAN must NOT bump the counter.
    loop._set_permission_mode(PermissionMode.PLAN)
    loop._set_permission_mode(PermissionMode.PLAN)
    assert loop._metrics.plan_mode_entries == 1


def test_set_permission_mode_idempotent_on_exit(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    # Already NORMAL; redundant transition to NORMAL must not bump any exit counter.
    loop._set_permission_mode(PermissionMode.NORMAL)
    loop._set_permission_mode(PermissionMode.NORMAL, source="slash")
    assert loop._metrics.plan_mode_exits_approved == 0
    assert loop._metrics.plan_mode_exits_manual == 0
    assert loop._metrics.plan_mode_exits_rejected == 0


def test_set_permission_mode_idempotent_does_not_emit_trace(tmp_path: Path) -> None:
    """No-op transitions also skip the permission trace emission — the trace
    surface mirrors the metric semantics."""
    loop = _make_loop(tmp_path)
    emits: list[dict[str, object]] = []
    original_emit = loop._tracer.emit

    def capture(channel: str, /, **fields: object) -> None:
        emits.append({"channel": channel, **fields})
        original_emit(channel, **fields)

    loop._tracer.emit = capture  # type: ignore[assignment]
    loop._set_permission_mode(PermissionMode.PLAN)
    loop._set_permission_mode(PermissionMode.PLAN)  # no-op
    loop._set_permission_mode(PermissionMode.PLAN, source="slash")  # no-op
    permission_emits = [e for e in emits if e["channel"] == "permission"]
    assert len(permission_emits) == 1  # only the real transition emitted
