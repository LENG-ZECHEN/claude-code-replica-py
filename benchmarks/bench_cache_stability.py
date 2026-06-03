"""Benchmark 2: Prompt-cache prefix stability — measured at the
``ToolResultStore`` boundary.

Why this matters
----------------
Anthropic's prompt-cache contract is "the cache hits if-and-only-if the
prefix bytes are identical across requests". The project's
``ContentReplacementState`` (src/simple_coding_agent/tool_result_store.py)
freezes the (tool_use_id → pointer string) decision after the first
externalization so the same ``tool_use_id`` always renders to a
bit-identical pointer even if the underlying content drifts between
rebuilds within a turn. A naive implementation that re-externalizes on
every rebuild produces a different ``preview=...`` field per call, which
would break the prefix and drop the cache hit rate to 0%.

Method
------
1. **Stable run**: real ``ToolResultStore`` with ``ContentReplacementState``.
   Call ``process_result`` 5 times with the same ``tool_use_id`` but
   slightly drifting content (simulating retries / streaming). Hash each
   returned pointer. Expect: 5/5 identical hashes.

2. **Naive run**: subclassed ``ToolResultStore`` whose cache is bypassed
   on every call. Same 5 calls with drifting content. Expect: 4/5 hashes
   differ (each rebuild produces a new preview, breaking prefix).

3. **Whole-prompt verification**: also rebuild a full context payload
   (system + messages) under both modes and hash the *full prefix*; the
   stable variant must produce 5/5 identical hashes, proving the
   end-to-end prompt cache contract holds.

Run:
    python -m benchmarks.bench_cache_stability
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from simple_coding_agent.context import ContextBudget, ContextBuilder
from simple_coding_agent.models import (
    Message,
    MessageType,
    Role,
    ToolCall,
    ToolResult,
)
from simple_coding_agent.tool_result_store import (
    ContentReplacementState,
    ToolResultStore,
)
from simple_coding_agent.transcript import Transcript

_ROUNDS = 5
_TOOL_USE_ID = "tu_cache_stab_001"
_BASE_TAIL = "x" * 60_000  # > 50KB threshold → externalizes
# Drift goes at the START so it lands inside the 2000-char preview window
# (PREVIEW_CHARS). Realistic example: shell output with a timestamp banner
# at the top. Each round's content is byte-different in the preview region,
# so a naive store that re-externalizes will compute a different pointer
# every time, while the cached store freezes the first decision.
_DRIFTING_PREFIXES = [
    "[run-1 timestamp: 2026-05-25T00:00:01Z]\nRunning command...\n",
    "[run-2 timestamp: 2026-05-25T00:00:02Z]\nRunning command...\n",
    "[run-3 timestamp: 2026-05-25T00:00:03Z]\nRunning command...\n",
    "[run-4 timestamp: 2026-05-25T00:00:04Z]\nRunning command...\n",
    "[run-5 timestamp: 2026-05-25T00:00:05Z]\nRunning command...\n",
]

_RESULTS_DIR = Path(__file__).resolve().parent / "_results"
_JSON_PATH = _RESULTS_DIR / "02_cache_stability.json"
_MD_PATH = _RESULTS_DIR / "02_cache_stability.md"


class _NoCache(ContentReplacementState):
    """ContentReplacementState that never remembers anything.

    Simulates the naive implementation where every rebuild re-externalizes
    and therefore produces a fresh preview block — the prompt-cache prefix
    is broken on every call.
    """

    def record(self, tool_use_id: str, pointer: str) -> None:  # noqa: ARG002
        return None

    def has_replacement(self, tool_use_id: str) -> bool:  # noqa: ARG002
        return False

    def get_replacement(self, tool_use_id: str) -> str | None:  # noqa: ARG002
        return None


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _run_pointer_stability(*, stable: bool) -> dict[str, object]:
    """Repeatedly process drifting content for one tool_use_id."""
    with tempfile.TemporaryDirectory(prefix="bench-cache-") as storage:
        store = ToolResultStore(storage_dir=storage)
        if not stable:
            store._replacement_state = _NoCache()  # bypass cache
        pointer_hashes: list[str] = []
        for i in range(_ROUNDS):
            content = _DRIFTING_PREFIXES[i] + _BASE_TAIL
            pointer, _stored = store.process_result(_TOOL_USE_ID, content)
            pointer_hashes.append(_hash(pointer))
    unique = len(set(pointer_hashes))
    return {
        "mode": "stable" if stable else "naive",
        "rounds": _ROUNDS,
        "pointer_hashes": pointer_hashes,
        "unique_hash_count": unique,
        "all_identical": unique == 1,
        "stability_score": f"{_ROUNDS - unique + 1}/{_ROUNDS}",
    }


def _build_transcript_with_tool_pair(
    tool_use_id: str, content: str
) -> Transcript:
    ts = datetime.now(UTC).isoformat()
    transcript = Transcript()
    transcript.append(Message.user("Show me the file."))
    transcript.append(Message(
        uuid=f"asst-{tool_use_id}",
        role=Role.ASSISTANT,
        content=[ToolCall(
            id=tool_use_id,
            name="read_file",
            input={"path": "src/big_module.py"},
        )],
        timestamp=ts,
        type=MessageType.TOOL_USE,
    ))
    transcript.append(Message(
        uuid=f"user-{tool_use_id}",
        role=Role.USER,
        content=[ToolResult(
            tool_use_id=tool_use_id,
            content=content,
        )],
        timestamp=ts,
        type=MessageType.TOOL_RESULT,
        is_meta=True,
    ))
    return transcript


def _run_full_context_stability(*, stable: bool) -> dict[str, object]:
    """Build a full context payload (system + messages) under both modes."""
    with tempfile.TemporaryDirectory(prefix="bench-cache-ctx-") as storage:
        store = ToolResultStore(storage_dir=storage)
        if not stable:
            store._replacement_state = _NoCache()
        budget = ContextBudget(max_tokens=100_000, reserved_output_tokens=4_096)
        builder = ContextBuilder(budget=budget, tool_result_store=store)

        prefix_hashes: list[str] = []
        for i in range(_ROUNDS):
            content = _DRIFTING_PREFIXES[i] + _BASE_TAIL
            transcript = _build_transcript_with_tool_pair(_TOOL_USE_ID, content)
            built = builder.build(
                transcript=transcript,
                system="You are a coding agent.",
            )
            payload = json.dumps(
                {"system": built.system, "messages": built.messages},
                sort_keys=True,
                ensure_ascii=False,
            )
            prefix_hashes.append(_hash(payload))
    unique = len(set(prefix_hashes))
    return {
        "mode": "stable" if stable else "naive",
        "rounds": _ROUNDS,
        "prefix_hashes": prefix_hashes,
        "unique_hash_count": unique,
        "all_identical": unique == 1,
        "stability_score": f"{_ROUNDS - unique + 1}/{_ROUNDS}",
    }


def _render_markdown(payload: dict[str, object]) -> str:
    p_stable = payload["pointer_stable"]
    p_naive = payload["pointer_naive"]
    c_stable = payload["context_stable"]
    c_naive = payload["context_naive"]
    lines = [
        "# Benchmark 2 — Prompt-Cache Prefix Stability",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        "",
        "## Scenario",
        "",
        f"For each round (5 total), the same `tool_use_id` ({_TOOL_USE_ID})",
        "is processed with **drifting content** (60 KB body + a per-round",
        "timestamp suffix). We hash either (a) the returned pointer string",
        "or (b) the full built context (system + messages) and count how",
        "many distinct hashes appear across the 5 rebuilds.",
        "",
        "Two configurations:",
        "- **Stable**: real `ContentReplacementState` (production default)",
        "- **Naive**: `ContentReplacementState` replaced with a no-op",
        "  (`_NoCache`) — simulates the naive implementation that",
        "  re-externalizes on every rebuild.",
        "",
        "## Pointer-level results",
        "",
        "| Mode | Rounds | Unique hashes | All identical? | Stability score |",
        "| ---- | ------ | ------------- | -------------- | --------------- |",
        f"| stable | {p_stable['rounds']} | "
        f"{p_stable['unique_hash_count']} | "
        f"{p_stable['all_identical']} | "
        f"**{p_stable['stability_score']}** |",
        f"| naive  | {p_naive['rounds']} | "
        f"{p_naive['unique_hash_count']} | "
        f"{p_naive['all_identical']} | "
        f"**{p_naive['stability_score']}** |",
        "",
        "## Full-context results (system + messages SHA-256)",
        "",
        "| Mode | Rounds | Unique hashes | All identical? | Stability score |",
        "| ---- | ------ | ------------- | -------------- | --------------- |",
        f"| stable | {c_stable['rounds']} | "
        f"{c_stable['unique_hash_count']} | "
        f"{c_stable['all_identical']} | "
        f"**{c_stable['stability_score']}** |",
        f"| naive  | {c_naive['rounds']} | "
        f"{c_naive['unique_hash_count']} | "
        f"{c_naive['all_identical']} | "
        f"**{c_naive['stability_score']}** |",
        "",
        "## Verdict",
        "",
        (
            "The stable implementation produces "
            f"**{p_stable['stability_score']}** identical pointers and "
            f"**{c_stable['stability_score']}** identical full-context "
            "prefixes, while the naive implementation produces "
            f"**{p_naive['stability_score']}** / "
            f"**{c_naive['stability_score']}** respectively. "
            "Prompt-cache prefix bytes only match when hashes are identical, "
            "so this is a direct measure of cache hit rate under content drift."
        ),
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "scenario": "Prompt-cache prefix stability under content drift",
        "rounds_per_mode": _ROUNDS,
        "drifting_prefix_examples": _DRIFTING_PREFIXES,
        "pointer_stable": _run_pointer_stability(stable=True),
        "pointer_naive": _run_pointer_stability(stable=False),
        "context_stable": _run_full_context_stability(stable=True),
        "context_naive": _run_full_context_stability(stable=False),
    }
    _JSON_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _MD_PATH.write_text(_render_markdown(payload), encoding="utf-8")

    p_s = payload["pointer_stable"]["stability_score"]
    p_n = payload["pointer_naive"]["stability_score"]
    c_s = payload["context_stable"]["stability_score"]
    c_n = payload["context_naive"]["stability_score"]
    print(f"[bench2] pointer stability:        stable={p_s} | naive={p_n}")
    print(f"[bench2] full-context stability:   stable={c_s} | naive={c_n}")
    print(f"[bench2] artifacts: {_JSON_PATH.name}, {_MD_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
