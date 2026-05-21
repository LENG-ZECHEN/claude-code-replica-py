"""End-to-end integration matrix — RUNTIME_ACTIVATION_PLAN.md section 3.5.

Scenario 1: a 30-turn scripted REPL session inside a tight context budget
must (a) flip ``LoopResult.compacted`` to True at least once and
(b) leave a ``COMPACT_BOUNDARY`` marker in the transcript.

Scenario 2: cross-process resume — Session A runs to compaction, saves;
Session B starts with ``--resume`` and the prior summary text must reach
its very first provider system prompt.

Scenario 3 (P9-M5): pre-seeded ``ProjectMemory`` feedback reaches the
loop's per-turn ``AgentStep.memory_injected`` AND the assembled
``built.system`` system prompt — proving that the Jaccard selector +
``_collect_memory_snippets`` + ``ContextBuilder`` chain is alive in the
default REPL wiring.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

import simple_coding_agent.claude_md as cm
import simple_coding_agent.cli as cli_mod
from simple_coding_agent.cli import main
from simple_coding_agent.models import MessageType
from simple_coding_agent.provider import MockProvider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_user_claude_md(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")


@pytest.fixture
def sessions_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> Path:
    d = tmp_path / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SIMPLE_AGENT_SESSIONS_DIR", str(d))
    return d


def _set_stdin(monkeypatch: pytest.MonkeyPatch, *lines: str) -> None:
    buffer = "\n".join(lines)
    if buffer and not buffer.endswith("\n"):
        buffer = buffer + "\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(buffer))


def _captured_loops() -> list[Any]:
    return list(getattr(cli_mod, "_LAST_LOOPS", []))


# ---------------------------------------------------------------------------
# Scenario 1: long conversation triggers full compact and leaves a boundary
# ---------------------------------------------------------------------------


def test_long_repl_session_triggers_full_compact_and_leaves_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    big = "x " * 5_000  # ~10 000 chars per turn
    answers = [
        MockProvider.direct_answer(big + f" turn {n}") for n in range(30)
    ]

    def _provider_factory(_ws: Path) -> Any:
        return MockProvider(answers)

    monkeypatch.setattr(cli_mod, "_make_repl_provider", _provider_factory)

    inputs = [f"turn {n}: " + big for n in range(30)] + ["/exit"]
    _set_stdin(monkeypatch, *inputs)

    rc = main([
        "--repl",
        "--workspace", str(tmp_path),
        "--max-context-tokens", "5000",
        "--reserved-output-tokens", "1000",
    ])
    assert rc == 0

    loop = _captured_loops()[0]
    boundaries = [
        m for m in loop._transcript.all_messages()
        if m.type == MessageType.COMPACT_BOUNDARY
    ]
    assert boundaries, "expected at least one COMPACT_BOUNDARY in the transcript"
    assert loop._last_summary is not None
    assert loop._metrics.full_compacts >= 1


# ---------------------------------------------------------------------------
# Scenario 2: cross-session resume preserves the compact summary text
# ---------------------------------------------------------------------------


def test_cross_session_resume_preserves_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sessions_dir: Path,
) -> None:
    big = "y " * 5_000
    answers_a = [
        MockProvider.direct_answer(big + f" turn {n}") for n in range(10)
    ]

    def _provider_a(_ws: Path) -> Any:
        return MockProvider(answers_a)

    monkeypatch.setattr(cli_mod, "_make_repl_provider", _provider_a)
    _set_stdin(
        monkeypatch,
        *([f"turn {n}: " + big for n in range(10)]
          + ["/save between", "/exit"]),
    )
    rc_a = main([
        "--repl",
        "--workspace", str(tmp_path / "a"),
        "--max-context-tokens", "5000",
        "--reserved-output-tokens", "1000",
    ])
    assert rc_a == 0

    saved = sessions_dir / "between.json"
    payload = json.loads(saved.read_text(encoding="utf-8"))
    assert payload["last_summary"] is not None
    expected_summary = payload["last_summary"]["summary_text"]

    captured_b: dict[str, MockProvider] = {}
    answers_b = [
        MockProvider.direct_answer(f"B reply {n}") for n in range(5)
    ]

    def _provider_b(_ws: Path) -> Any:
        p = MockProvider(answers_b)
        captured_b["p"] = p
        return p

    monkeypatch.setattr(cli_mod, "_make_repl_provider", _provider_b)
    _set_stdin(
        monkeypatch,
        *([f"resumed turn {n}" for n in range(5)] + ["/exit"]),
    )
    rc_b = main([
        "--repl",
        "--resume", "between",
        "--workspace", str(tmp_path / "b"),
    ])
    assert rc_b == 0

    systems = [c.system for c in captured_b["p"].history]
    assert systems, "resumed REPL should have driven at least one provider call"
    assert expected_summary in systems[0]
    assert "## Conversation Summary" in systems[0]


# ---------------------------------------------------------------------------
# Scenario 3 (P9-M5): seeded ProjectMemory snippet reaches built.system
# ---------------------------------------------------------------------------


def test_seeded_project_memory_reaches_built_system_prompt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Seed a feedback entry, drive one REPL turn, then re-run via the
    same loop to read back ``step.memory_injected``. The three pass
    criteria from plan 3.5 #3 are: (a) ``step.memory_injected`` non-empty
    and contains the snippet, (b) the snippet is present in
    ``built.system``, proven via the provider's recorded system prompt.
    """
    from simple_coding_agent.memory import MemoryEntry, MemoryType, ProjectMemory

    memory_root = tmp_path / "project-memory"
    monkeypatch.setenv("SIMPLE_AGENT_MEMORY_DIR", str(memory_root))
    seeded_body = "user prefers tabs over spaces in Python files"
    ProjectMemory(storage_dir=str(memory_root)).save(MemoryEntry(
        name="tabs_pref",
        body=seeded_body,
        type=MemoryType.FEEDBACK,
        id="tabs_pref",
    ))

    captured_provider: dict[str, MockProvider] = {}
    answers = [
        MockProvider.direct_answer("hello world program acknowledged"),
        MockProvider.direct_answer("second turn reply"),
    ]

    def _provider_factory(_ws: Path) -> Any:
        p = MockProvider(answers)
        captured_provider["p"] = p
        return p

    monkeypatch.setattr(cli_mod, "_make_repl_provider", _provider_factory)
    _set_stdin(monkeypatch, "write a hello world program", "/exit")

    rc = main(["--repl", "--workspace", str(tmp_path / "ws")])
    assert rc == 0

    loop = _captured_loops()[0]
    assert loop._project_memory is not None

    # (b) built.system contains the snippet -- read it off the provider's
    # recorded system prompt for the REPL's only turn.
    history = captured_provider["p"].history
    assert history, "expected at least one provider call"
    first_system = history[0].system
    assert "## Memory" in first_system
    assert seeded_body in first_system

    # (a) step.memory_injected non-empty and contains the snippet. Drive
    # one direct turn on the same loop so we can inspect AgentStep.
    direct = loop.run("write a hello world program")
    assert direct.steps, "expected at least one AgentStep from the direct run"
    injected = direct.steps[0].memory_injected
    assert injected, "memory_injected should be populated on the first step"
    assert any(seeded_body in snippet for snippet in injected)
    assert any(snippet.startswith("[feedback] tabs_pref") for snippet in injected)
