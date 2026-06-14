"""DreamConsolidator: periodic memory consolidation engine.

Source mapping:
  buildConsolidationPrompt  <- autoDream/consolidationPrompt.ts:10
    (4-stage Orient/Gather/Consolidate/Prune+Index prompt, ported verbatim in spirit)
  createAutoMemCanUseTool   <- extractMemories/extractMemories.ts:171
    (memory-dir-scoped can_use_tool gate mirrored in DreamConsolidator._can_use_tool)
  runAutoDream              <- autoDream/autoDream.ts
    (gate cascade reused from M5 consolidation_lock.should_dream)

Design decisions:
  - LLM mode (provider is not None): ForkedAgentRunner with 4-stage prompt +
    memory-dir gate. Deterministic fallback (provider=None): Jaccard dedup + prune.
  - HIGH_JACCARD_THRESHOLD = 0.80 (safety knob, conservative):
    Only entries with ≥80% token overlap are treated as near-identical duplicates.
    Trade-off: very low false-positive rate (entries sharing a few keywords but
    carrying different semantics score ≤0.40 and are left untouched) while
    correctly catching entries with identical bodies but differing short names
    (which score ≈0.85 — above the 0.80 line, clearly duplicate content).
    Idempotency follows naturally: once a duplicate is removed, no near-identical
    pair survives, so a second dream always returns merged=0, pruned=0.
  - MANIFEST_MAX_ENTRIES = 200 matches MAX_ENTRYPOINT_LINES from memdir.ts
    (the MEMORY.md index cap). After dedup, entries beyond this limit are pruned
    oldest-first by mtime.
  - All writes via ProjectMemory.save() / .delete() — M1's _SAFE_ENTRY_ID_PATTERN +
    is_relative_to() path-traversal guard and secret-detection remain in force.
  - M5 consolidation_lock.should_dream() is the single source of truth for gating.
    M6 does NOT re-implement any gate logic.
  - recordConsolidation (consolidationLock.ts:130) is deferred to M7, which owns
    the CLI dream subcommand and will stamp the lock after a successful dream.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .coding_tools import (
    WRITE_MEMORY_ENTRY_SCHEMA,
    WRITE_MEMORY_ENTRY_TOOL_DESCRIPTION,
    WRITE_MEMORY_ENTRY_TOOL_NAME,
    SearchMatch,
    list_files,
    read_file,
    search_text,
    write_memory_entry,
)
from .consolidation_lock import (
    MIN_HOURS,
    MIN_SESSIONS,
    DreamGateDecision,
    record_consolidation,
    rollback_consolidation_lock,
    should_dream,
)
from .forked_agent import ForkedAgentRunner
from .memdir import scan_memory_files
from .memory import MemorySelector, ProjectMemory
from .provider import Provider
from .tools import Tool, ToolRegistry

__all__ = ["DreamConsolidator", "DreamResult"]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_DREAM_TURNS: int = 20  # consolidationPrompt.ts: more complex than extraction (5 turns)

# Conservative dedup threshold — only collapses entries with ≥80% token overlap.
# Trade-off documented in module docstring above. Visible in: _run_deterministic_consolidation.
# Why 0.80 (not 0.85): two entries with identical bodies but slightly different names
# (e.g., "entry-a" vs "entry-b" → "Entry A" vs "Entry B" in frontmatter) yield
# Jaccard ≈ 0.846, which is unambiguously duplicate content. Threshold 0.80 catches
# these while remaining well above the ~0.25–0.40 range of semantically-similar-but-
# distinct entries (e.g., "user prefers short answers" vs "prefer concise explanations").
HIGH_JACCARD_THRESHOLD: float = 0.80

# Matches MAX_ENTRYPOINT_LINES from memdir.ts: maximum entries in MEMORY.md index.
MANIFEST_MAX_ENTRIES: int = 200


# ---------------------------------------------------------------------------
# DreamResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DreamResult:
    """Outcome of one DreamConsolidator.consolidate() call.

    merged:        near-identical pairs collapsed (deterministic) or entries
                   written by the LLM agent (LLM mode).
    pruned:        entries removed in the mtime-based prune step after dedup
                   (deterministic only; 0 in LLM mode).
    runs:          ForkedAgentRunner invocations (0 = deterministic path).
    written_paths: absolute paths of .md files written (LLM mode only; () otherwise).
    """

    merged: int
    pruned: int
    runs: int
    written_paths: tuple[str, ...]


# ---------------------------------------------------------------------------
# 4-stage consolidation prompt
# Source: autoDream/consolidationPrompt.ts:10  buildConsolidationPrompt
# ---------------------------------------------------------------------------


def _build_dream_prompt(memory_dir: Path, sessions_since: tuple[str, ...]) -> str:
    """Port of buildConsolidationPrompt from autoDream/consolidationPrompt.ts:10.

    Anti-turn-waste directives verbatim in spirit (consolidationPrompt.ts:10):
      "grep narrowly, don't read whole files"
      "Look only for things you already suspect matter"
    Session list fed in so the agent doesn't waste turns finding scope.
    """
    session_block = (
        "\n".join(f"  - {sid}" for sid in sessions_since)
        if sessions_since
        else "  (no sessions found)"
    )
    return (
        f"# Dream: Memory Consolidation\n\n"
        f"You are performing a dream — a reflective pass over your memory files. "
        f"Synthesize what you've learned recently into durable, well-organized "
        f"memories so that future sessions can orient quickly.\n\n"
        f"Memory directory: `{memory_dir}`\n\n"
        f"Sessions modified since last consolidation:\n{session_block}\n\n"
        f"---\n\n"
        f"## Phase 1 — Orient\n\n"
        f"- Use `list_files` on the memory directory to see what already exists\n"
        f"- Read `MEMORY.md` with `read_file` to understand the current index\n"
        f"- Skim existing topic files to improve them rather than creating duplicates\n\n"
        f"## Phase 2 — Gather recent signal\n\n"
        f"Concentrate on the sessions listed above — that is the relevant scope.\n"
        f"Use `search_text` with **narrow terms** to find specific context. "
        f"Look only for things you already suspect matter. "
        f"Do NOT exhaustively read all files.\n\n"
        f"## Phase 3 — Consolidate\n\n"
        f"For each thing worth remembering, write or update a memory file using "
        f"`write_memory_entry`.\n\n"
        f"Focus on:\n"
        f"- Merging new signal into existing topic files rather than creating near-duplicates\n"
        f"- Converting relative dates to absolute dates so they remain interpretable\n"
        f"- Removing contradicted facts — fix stale memories at their source\n\n"
        f"## Phase 4 — Prune and index\n\n"
        f"Ensure `MEMORY.md` stays under {MANIFEST_MAX_ENTRIES} lines. "
        f"It is an **index**, not a dump — each entry should be one line under "
        f"~150 characters: `- [Title](file.md) — one-line hook`.\n\n"
        f"- Remove pointers to memories that are stale, wrong, or superseded\n"
        f"- Add pointers to newly important memories\n"
        f"- Resolve contradictions between files\n\n"
        f"---\n\n"
        f"Return a brief summary of what you consolidated, updated, or pruned. "
        f"If nothing changed (memories are already tight), say so."
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _format_search(matches: list[SearchMatch]) -> str:
    """Render SearchMatch list as a grep-style block (mirrors tool_registry_factory)."""
    if not matches:
        return "(no matches)"
    return "\n".join(f"{m.path}:{m.line_no}: {m.preview}" for m in matches)


# Allowed read-only tool names (createAutoMemCanUseTool analog: extractMemories.ts:171)
_READ_ONLY_TOOLS: frozenset[str] = frozenset({"read_file", "list_files", "search_text"})


# ---------------------------------------------------------------------------
# DreamConsolidator
# ---------------------------------------------------------------------------


class DreamConsolidator:
    """Periodic memory consolidation engine.

    LLM mode (provider is not None): ForkedAgentRunner executes the 4-stage
    consolidation prompt. Deterministic fallback (provider=None): Jaccard dedup
    + mtime-based prune, no provider calls.

    Gating delegates entirely to M5's consolidation_lock.should_dream —
    no gate logic is re-implemented here.
    """

    def __init__(
        self,
        memory_dir: Path | str,
        provider: Provider | None = None,
        sessions_dir: Path | str | None = None,
        max_turns: int = MAX_DREAM_TURNS,
    ) -> None:
        self._memory_dir = Path(memory_dir).resolve()
        self._provider = provider
        self._sessions_dir = Path(sessions_dir).resolve() if sessions_dir else None
        self._max_turns = max_turns

    def consolidate(
        self,
        lock_path: Path | str,
        *,
        now_ms: float | None = None,
        last_scan_at_ms: float = 0.0,
        current_session_id: str | None = None,
        min_hours: float = MIN_HOURS,
        min_sessions: int = MIN_SESSIONS,
        enabled: bool = True,
        pid: int | None = None,
        is_process_running_fn: Callable[[int], bool] | None = None,
    ) -> DreamResult:
        """Run dream consolidation if the gate cascade passes.

        Gate: consolidation_lock.should_dream (M5 — five-stage cheapest-first).
        When gate passes: LLM path (ForkedAgentRunner) if provider is set,
        deterministic Jaccard/prune path otherwise. On any exception after
        lock acquisition, rollback_consolidation_lock is called so the time
        gate re-opens (M5 rollback contract).
        """
        now = now_ms if now_ms is not None else time.time() * 1000.0
        decision = should_dream(
            lock_path,
            self._sessions_dir,
            enabled=enabled,
            now_ms=now,
            last_scan_at_ms=last_scan_at_ms,
            current_session_id=current_session_id,
            min_hours=min_hours,
            min_sessions=min_sessions,
            pid=pid,
            is_process_running_fn=is_process_running_fn,
        )
        if not decision.should_dream:
            return DreamResult(merged=0, pruned=0, runs=0, written_paths=())

        try:
            if self._provider is not None:
                result = self._run_llm_consolidation(decision)
            else:
                result = self._run_deterministic_consolidation()
        except Exception:
            rollback_consolidation_lock(lock_path, decision.prior_mtime or 0.0)
            raise

        # Stamp the lock so the time gate re-opens after MIN_HOURS.
        # consolidationLock.ts:130 recordConsolidation (deferred from M6).
        record_consolidation(lock_path, now)
        return result

    # ------------------------------------------------------------------
    # LLM path
    # ------------------------------------------------------------------

    def _run_llm_consolidation(self, decision: DreamGateDecision) -> DreamResult:
        """Run ForkedAgentRunner with the 4-stage prompt and memory-dir gate.

        context_messages=[] — dream reads from disk via tools, passes no
        conversation context (PLAN note: "Dream passes none; it reads from
        disk via tools").
        """
        assert self._provider is not None  # caller guarantees this
        written_paths: list[str] = []
        local_pm = ProjectMemory(str(self._memory_dir))
        registry = self._build_dream_registry(written_paths, local_pm)

        runner = ForkedAgentRunner(
            provider=self._provider,
            system_prompt=(
                "You are a memory consolidation agent. You have access to "
                "list_files, read_file, search_text, and write_memory_entry tools. "
                "Use them to consolidate and organize memory files."
            ),
            can_use_tool=self._can_use_tool,
            tool_registry=registry,
            max_turns=self._max_turns,
        )
        task_prompt = _build_dream_prompt(self._memory_dir, decision.sessions_since)
        runner.run(task_prompt=task_prompt, context_messages=[])

        return DreamResult(
            merged=len(written_paths),
            pruned=0,
            runs=1,
            written_paths=tuple(written_paths),
        )

    def _can_use_tool(self, name: str, inp: dict[str, Any]) -> tuple[bool, str]:
        """Memory-dir-scoped gate mirroring createAutoMemCanUseTool (extractMemories.ts:171).

        Allow: read_file, list_files, search_text (read-only, unconditional).
               write_memory_entry (ProjectMemory.save enforces path-traversal +
               secret guards — those are the primary defenses; this gate is
               defense-in-depth).
        Deny: everything else with a clear reason.
        """
        if name in _READ_ONLY_TOOLS or name == WRITE_MEMORY_ENTRY_TOOL_NAME:
            return True, ""
        allowed = ", ".join(sorted(_READ_ONLY_TOOLS)) + f", {WRITE_MEMORY_ENTRY_TOOL_NAME}"
        return False, (
            f"Tool '{name}' is not available in the dream consolidation context. "
            f"Only {allowed} are allowed."
        )

    def _build_dream_registry(
        self,
        written_paths: list[str],
        local_pm: ProjectMemory,
    ) -> ToolRegistry:
        """Build a ToolRegistry for the dream agent.

        Mirrors _build_restricted_registry in extract_memories.py:
          read-only tools bound to memory_dir as workspace;
          write_memory_entry closes over local_pm and written_paths.
        """
        ws = self._memory_dir
        registry = ToolRegistry()

        registry.register(Tool(
            name="list_files",
            description="List files in the memory directory as POSIX relative paths.",
            input_schema={
                "type": "object",
                "properties": {"subdir": {"type": "string"}},
            },
            fn=lambda subdir=None: "\n".join(list_files(ws, subdir=subdir)),
            read_only=True,
        ))

        registry.register(Tool(
            name="read_file",
            description="Read a UTF-8 text file inside the memory directory.",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            fn=lambda path: read_file(ws, path),
            read_only=True,
        ))

        registry.register(Tool(
            name="search_text",
            description="Search for text patterns within the memory directory.",
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "subdir": {"type": "string"},
                },
                "required": ["pattern"],
            },
            fn=lambda pattern, subdir=None: _format_search(
                search_text(ws, pattern, subdir=subdir)
            ),
            read_only=True,
        ))

        memory_dir_ref = self._memory_dir

        def _tracked_write(**kwargs: Any) -> str:
            result = write_memory_entry(project_memory=local_pm, **kwargs)
            entry_id = kwargs.get("id", "")
            abs_path = str((memory_dir_ref / f"{entry_id}.md").resolve())
            written_paths.append(abs_path)
            return result

        registry.register(Tool(
            name=WRITE_MEMORY_ENTRY_TOOL_NAME,
            description=WRITE_MEMORY_ENTRY_TOOL_DESCRIPTION,
            input_schema=WRITE_MEMORY_ENTRY_SCHEMA,
            fn=_tracked_write,
        ))

        return registry

    # ------------------------------------------------------------------
    # Deterministic path
    # ------------------------------------------------------------------

    def _run_deterministic_consolidation(self) -> DreamResult:
        """Jaccard dedup + mtime-based prune. No provider calls.

        Algorithm:
          1. Load all entries and their mtimes.
          2. O(N²) pairwise Jaccard scoring at HIGH_JACCARD_THRESHOLD.
             Keep NEWEST by mtime; mark older for deletion.
          3. Delete marked entries via ProjectMemory.delete().
          4. If remaining count > MANIFEST_MAX_ENTRIES, delete oldest-by-mtime
             entries until within the limit.
          5. Return DreamResult(merged, pruned, runs=0, written_paths=()).

        All deletes via ProjectMemory.delete() to keep M1's path-traversal
        guard and secret-detection in force.
        Immutable: entry list is never mutated; new collections are built.
        """
        pm = ProjectMemory(str(self._memory_dir))
        headers = scan_memory_files(self._memory_dir)
        entries = pm.all()

        header_mtime: dict[str, float] = {h.id: h.mtime for h in headers}
        selector = MemorySelector()
        to_delete: set[str] = set()

        # Step 1: Jaccard-based dedup — O(N²), safe for up to ~300 entries.
        for i, e1 in enumerate(entries):
            if e1.id in to_delete:
                continue
            for e2 in entries[i + 1:]:
                if e2.id in to_delete:
                    continue
                text1 = " ".join([e1.name, e1.body, *e1.tags])
                text2 = " ".join([e2.name, e2.body, *e2.tags])
                if selector.score(text1, text2) < HIGH_JACCARD_THRESHOLD:
                    continue
                mtime1 = header_mtime.get(e1.id, 0.0)
                mtime2 = header_mtime.get(e2.id, 0.0)
                # Keep newer; delete older (ties go to e2 — arbitrary but stable).
                to_delete.add(e1.id if mtime1 <= mtime2 else e2.id)

        merged = len(to_delete)
        for entry_id in to_delete:
            pm.delete(entry_id)

        # Step 2: Mtime-based prune — remove oldest if count > MANIFEST_MAX_ENTRIES.
        # headers are sorted newest-first by scan_memory_files; prune from the tail.
        remaining_headers = [h for h in headers if h.id not in to_delete]
        pruned = 0
        if len(remaining_headers) > MANIFEST_MAX_ENTRIES:
            excess = remaining_headers[MANIFEST_MAX_ENTRIES:]
            for h in excess:
                pm.delete(h.id)
                pruned += 1

        return DreamResult(
            merged=merged,
            pruned=pruned,
            runs=0,
            written_paths=(),
        )
