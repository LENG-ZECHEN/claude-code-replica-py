"""
SessionMemoryState: frozen accumulator for the running SM compact summary.

Source mapping:
  SessionMemoryState       <- session memory state held between turns;
                              mirrors src/services/SessionMemory/ (TS source)
  to_jsonable/from_jsonable <- forward-compat round-trip pattern mirroring
                               Transcript.to_jsonable/from_jsonable in transcript.py
  update_session_memory    <- incremental deterministic fold; analogous to the
                              per-turn SM update in
                              src/services/SessionMemory/prompts.ts (M2 uses
                              RuleBasedSummarizer; the LLM updater is M3)
  _MAX_SECTION_CHARS       <- analogous to MAX_SECTION_LENGTH = 2000 (tokens)
                              in src/services/SessionMemory/prompts.ts:8;
                              converted to chars at ~4 chars/token
  _MAX_TOTAL_CHARS         <- analogous to MAX_TOTAL_SESSION_MEMORY_TOKENS = 12_000
                              in src/services/SessionMemory/prompts.ts:9

Section set (9 sections — mirrors RuleBasedSummarizer's output in compact.py:165-189):
  1. Primary Request and Intent
  2. Key Technical Concepts
  3. Files and Code Sections
  4. Errors Encountered
  5. Problem Solving
  6. All User Messages
  7. Pending Tasks
  8. Current Work
  9. Optional Next Step

Design rationale:
  - Sections stored as tuple[tuple[str, str], ...] (name, content) pairs in
    canonical order — immutable, hashable, round-trippable.
  - `is_warm` / `is_empty` let the consumer (SessionMemorySummarizer in compact.py)
    branch cheaply without inspecting section contents.
  - `from_jsonable` silently ignores unknown keys (forward-compat): a future M3/M4
    JSON field must not crash an old reader. Unknown section keys in the sections
    dict are also silently dropped, preserving only the canonical 9 names.
  - `update_session_memory` calls the public `RuleBasedSummarizer().summarize()` to
    extract sections, then applies per-section + total caps before returning a new
    frozen state. Input state and messages are never mutated (frozen dataclass).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .models import Message

__all__ = ["SessionMemoryState", "update_session_memory", "update_session_memory_llm"]

# Tool name for the LLM-mode updater's capture tool (mirrors createMemoryFileCanUseTool
# from src/services/SessionMemory/sessionMemory.ts:460 — the "Edit one file only" gate)
_SM_WRITE_TOOL_NAME = "write_session_memory_summary"

# ---------------------------------------------------------------------------
# Section vocabulary (mirrors RuleBasedSummarizer order in compact.py:165-189)
# ---------------------------------------------------------------------------

_SECTION_NAMES: tuple[str, ...] = (
    "Primary Request and Intent",
    "Key Technical Concepts",
    "Files and Code Sections",
    "Errors Encountered",
    "Problem Solving",
    "All User Messages",
    "Pending Tasks",
    "Current Work",
    "Optional Next Step",
)

# Per-section char cap: 2000 tokens × ~4 chars/token
# Source: MAX_SECTION_LENGTH = 2000 in src/services/SessionMemory/prompts.ts:8
_MAX_SECTION_CHARS: int = 8_000

# Total char cap: 12_000 tokens × ~4 chars/token
# Source: MAX_TOTAL_SESSION_MEMORY_TOKENS = 12_000 in prompts.ts:9
_MAX_TOTAL_CHARS: int = 48_000

_VERSION: int = 1

# Matches "N. Section Name:\n<content>" blocks separated by blank lines.
# Uses a non-greedy match terminated by the next numbered section or end-of-string.
_SECTION_BLOCK_RE = re.compile(
    r"^\d+\.\s+(?P<name>.+?):\n(?P<content>.*?)(?=\n\n\d+\.|$)",
    re.DOTALL | re.MULTILINE,
)


# ---------------------------------------------------------------------------
# SessionMemoryState
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SessionMemoryState:
    """Frozen accumulator holding the running 9-section SM compact summary.

    Each section is a (name, content) pair stored in canonical order.
    Use `SessionMemoryState.empty()` to create a cold (empty) state.
    """

    sections: tuple[tuple[str, str], ...]

    # --- Factory ---

    @classmethod
    def empty(cls) -> SessionMemoryState:
        """Return a cold state with all sections blank."""
        return cls(sections=tuple((name, "") for name in _SECTION_NAMES))

    # --- State predicates ---

    @property
    def is_warm(self) -> bool:
        """True when at least one section has non-blank content."""
        return any(content.strip() for _, content in self.sections)

    @property
    def is_empty(self) -> bool:
        return not self.is_warm

    # --- Rendering ---

    def render(self) -> str:
        """Render sections as a human-readable string in the same format as
        RuleBasedSummarizer.summarize() so the two surfaces are structurally
        identical when called on equivalent message sets."""
        parts = [
            f"{i}. {name}:\n{content}"
            for i, (name, content) in enumerate(self.sections, 1)
        ]
        return "\n\n".join(parts)

    # --- Serialization ---

    def to_jsonable(self) -> dict[str, Any]:
        """Return a JSON-ready dict for storage or cross-process transfer."""
        return {
            "version": _VERSION,
            "sections": {name: content for name, content in self.sections},
        }

    @classmethod
    def from_jsonable(cls, data: dict[str, Any]) -> SessionMemoryState:
        """Reconstruct from a to_jsonable() dict.

        Unknown top-level keys and unknown section keys are silently ignored
        (forward-compat). A missing 'sections' key returns an empty state.
        A structurally invalid known field raises ValueError.
        """
        if not isinstance(data, dict):
            raise ValueError(
                f"SessionMemoryState payload must be a JSON object, "
                f"got {type(data).__name__}"
            )
        raw_sections = data.get("sections")
        if raw_sections is None:
            return cls.empty()
        if not isinstance(raw_sections, dict):
            raise ValueError(
                f"SessionMemoryState 'sections' field must be a dict, "
                f"got {type(raw_sections).__name__}"
            )
        built: list[tuple[str, str]] = []
        for name in _SECTION_NAMES:
            content = raw_sections.get(name, "")
            if not isinstance(content, str):
                raise ValueError(
                    f"SessionMemoryState section '{name}' must be a string, "
                    f"got {type(content).__name__}"
                )
            built.append((name, content))
        return cls(sections=tuple(built))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_sections(text: str) -> dict[str, str]:
    """Parse RuleBasedSummarizer numbered-section output into a name→content map.

    Each block has the form:
      N. Section Name:\\n<content>

    Blocks are separated by blank lines. Unknown section names are kept in the
    dict but filtered out when building a SessionMemoryState (only canonical
    names land in the state).
    """
    result: dict[str, str] = {}
    for match in _SECTION_BLOCK_RE.finditer(text):
        name = match.group("name").strip()
        content = match.group("content").strip()
        result[name] = content
    return result


def _cap_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"... [truncated at {max_chars} chars]"


def _apply_caps(sections_map: dict[str, str]) -> tuple[tuple[str, str], ...]:
    """Build the canonical sections tuple, applying per-section + total caps."""
    built: list[tuple[str, str]] = []
    total = 0
    for name in _SECTION_NAMES:
        content = sections_map.get(name, "")
        capped = _cap_text(content, _MAX_SECTION_CHARS)
        remaining = _MAX_TOTAL_CHARS - total
        if remaining <= 0:
            built.append((name, ""))
        elif len(capped) > remaining:
            built.append((name, capped[:remaining]))
        else:
            built.append((name, capped))
        total += len(built[-1][1])
    return tuple(built)


# ---------------------------------------------------------------------------
# update_session_memory
# ---------------------------------------------------------------------------

def update_session_memory(
    state: SessionMemoryState,
    new_messages: list[Message],
) -> SessionMemoryState:
    """Fold new_messages into state, returning a NEW SessionMemoryState.

    Immutable: state and new_messages are never mutated.
    Uses RuleBasedSummarizer's 9-section heuristics to extract section content
    from new_messages, then applies per-section (_MAX_SECTION_CHARS) and total
    (_MAX_TOTAL_CHARS) caps so the warm state cannot grow unbounded.

    Source: analogous to the per-turn SM update path in
    src/services/SessionMemory/prompts.ts (M2 uses the deterministic
    RuleBasedSummarizer; the LLM-backed updater is M3).

    Producer/consumer split:
      - This function is the PRODUCER (called per-turn in M3).
      - SessionMemorySummarizer.summarize() is the CONSUMER (called at
        compaction time), returning the prewarmed text with O(0) provider calls.
    """
    if not new_messages:
        return state

    # Lazy import avoids circular import (compact.py will import
    # SessionMemoryState from this module at load time).
    from .compact import RuleBasedSummarizer  # noqa: PLC0415

    summary_text = RuleBasedSummarizer().summarize(new_messages)
    if not summary_text:
        return state

    new_parsed = _parse_sections(summary_text)

    # Merge: prefer new content for each section; fall back to previous state.
    prev_dict: dict[str, str] = {name: content for name, content in state.sections}
    merged: dict[str, str] = {}
    for name in _SECTION_NAMES:
        new_val = new_parsed.get(name, "")
        merged[name] = new_val if new_val else prev_dict.get(name, "")

    return SessionMemoryState(sections=_apply_caps(merged))


# ---------------------------------------------------------------------------
# update_session_memory_llm
# ---------------------------------------------------------------------------


def update_session_memory_llm(
    state: SessionMemoryState,
    new_messages: list[Message],
    provider: Any,
) -> SessionMemoryState:
    """LLM-mode SM updater via ForkedAgentRunner.

    Uses a capture tool to receive the LLM's updated sections JSON, mirroring
    the TS createMemoryFileCanUseTool gate (sessionMemory.ts:460) — the "Edit
    one file only" path. Here, the single permitted tool is
    'write_session_memory_summary', analogous to allowing edits of only the SM
    file. The gate denies all other tool names.

    Falls back to the deterministic update_session_memory fold if the LLM does
    not call the capture tool (e.g., MockProvider scripted to return text).

    Source mapping:
      createMemoryFileCanUseTool <- src/services/SessionMemory/sessionMemory.ts:460
      streamCompactSummary       <- src/services/compact/compact.ts:1136
        (the LLM call we SKIP at compaction when warm state is available)
    """
    if not new_messages:
        return state

    # Lazy imports — forked_agent + tools import nothing from this module.
    from .forked_agent import ForkedAgentRunner  # noqa: PLC0415
    from .tools import Tool, ToolRegistry  # noqa: PLC0415

    captured_sections: dict[str, str] = {}

    def _write_summary(sections: dict[str, str]) -> str:
        captured_sections.update(
            {k: str(v) for k, v in sections.items() if isinstance(k, str)}
        )
        return "Session memory updated."

    registry = ToolRegistry()
    registry.register(Tool(
        name=_SM_WRITE_TOOL_NAME,
        description="Write the updated session memory summary sections.",
        input_schema={
            "type": "object",
            "properties": {
                "sections": {
                    "type": "object",
                    "description": "Mapping of section name to updated content.",
                }
            },
            "required": ["sections"],
        },
        fn=lambda sections: _write_summary(sections),
    ))

    def _can_use_tool(name: str, _input: dict[str, Any]) -> tuple[bool, str]:
        if name != _SM_WRITE_TOOL_NAME:
            return False, f"Only '{_SM_WRITE_TOOL_NAME}' is permitted in SM updater."
        return True, ""

    system_prompt = (
        "You are a session memory updater. Review the current session memory and "
        "the new messages, then call write_session_memory_summary with an updated "
        "sections dict. Return all canonical section names with updated content."
    )

    context_text = state.render() if state.is_warm else "(no prior session memory)"
    messages_text = "\n".join(
        f"{m.role.value}: {m.content if isinstance(m.content, str) else '[tool content]'}"
        for m in new_messages
    )
    task_prompt = (
        f"Current session memory:\n{context_text}\n\n"
        f"New messages to integrate:\n{messages_text}\n\n"
        f"Call write_session_memory_summary with the updated sections."
    )

    runner = ForkedAgentRunner(
        provider=provider,
        system_prompt=system_prompt,
        can_use_tool=_can_use_tool,
        tool_registry=registry,
        max_turns=3,
    )
    runner.run(task_prompt)

    if not captured_sections:
        # LLM didn't call the capture tool; fall back to deterministic fold.
        return update_session_memory(state, new_messages)

    prev_dict: dict[str, str] = dict(state.sections)
    merged: dict[str, str] = {
        name: captured_sections.get(name, prev_dict.get(name, ""))
        for name in _SECTION_NAMES
    }
    return SessionMemoryState(sections=_apply_caps(merged))
