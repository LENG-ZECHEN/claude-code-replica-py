"""
Tool result externalization store.

Source mapping:
  ToolResultStore        <- src/utils/toolResultStorage.ts
  StoredResult           <- ToolResultStorageEntry in toolResultStorage.ts
  ContentReplacementState <- ContentReplacementState in toolResultStorage.ts
  PERSISTED_OUTPUT_TAG   <- "<persisted-output>" tag in toolResultStorage.ts
  DEFAULT_MAX_INLINE_CHARS <- maxResultSizeChars = 50_000 in src/Tool.ts

When a tool result exceeds DEFAULT_MAX_INLINE_CHARS, the full content is
written to disk and the in-context representation is replaced with a compact
pointer containing the file path and a short preview.  ContentReplacementState
records decisions once so the same tool_use_id always gets the same pointer
(cache stability across repeated API calls).

DEFAULT_TOTAL_BUDGET_CHARS caps the total inline size of all tool results in
one context build.  After the per-item pass, if the sum of remaining inline
content exceeds this limit the largest items are externalized first until the
total drops back under budget.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass

from .tools import PREVIEW_CHARS as _PREVIEW_CHARS
from .tools import preview_result

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PERSISTED_OUTPUT_TAG: str = "<persisted-output>"
PREVIEW_CHARS: int = _PREVIEW_CHARS          # 2_000
DEFAULT_MAX_INLINE_CHARS: int = 50_000
DEFAULT_TOTAL_BUDGET_CHARS: int = 200_000


# ---------------------------------------------------------------------------
# StoredResult
# ---------------------------------------------------------------------------

@dataclass
class StoredResult:
    """Record of one externalized tool result.

    Source: ToolResultStorageEntry in src/utils/toolResultStorage.ts.
    """
    tool_use_id: str
    path: str
    original_size: int
    preview: str


# ---------------------------------------------------------------------------
# ContentReplacementState
# ---------------------------------------------------------------------------

class ContentReplacementState:
    """Freezes pointer decisions so the same tool_use_id always maps to the
    same pointer string across repeated API calls.

    Source: ContentReplacementState in src/utils/toolResultStorage.ts.
    """

    def __init__(self) -> None:
        self._replacements: dict[str, str] = {}

    def record(self, tool_use_id: str, pointer: str) -> None:
        """Record a pointer for tool_use_id; ignored if already recorded."""
        if tool_use_id not in self._replacements:
            self._replacements[tool_use_id] = pointer

    def has_replacement(self, tool_use_id: str) -> bool:
        return tool_use_id in self._replacements

    def get_replacement(self, tool_use_id: str) -> str | None:
        return self._replacements.get(tool_use_id)


# ---------------------------------------------------------------------------
# ToolResultStore
# ---------------------------------------------------------------------------

class ToolResultStore:
    """Persists oversized tool results to disk and tracks their pointers.

    Source: toolResultStorage utilities in src/utils/toolResultStorage.ts.

    Two budget checks applied by process_results_batch():
      1. Per-item: any result > max_inline_chars is externalized immediately.
      2. Total: if the sum of remaining inline content exceeds
         total_budget_chars, the largest items are externalized until the
         total drops back under budget.

    ContentReplacementState ensures that once a tool_use_id has been
    externalized, all subsequent calls return the same pointer (prompt-cache
    stability across repeated context rebuilds within a turn).
    """

    def __init__(
        self,
        max_inline_chars: int = DEFAULT_MAX_INLINE_CHARS,
        total_budget_chars: int = DEFAULT_TOTAL_BUDGET_CHARS,
        storage_dir: str | None = None,
    ) -> None:
        self._max_inline_chars = max_inline_chars
        self._total_budget_chars = total_budget_chars
        self._storage_dir = storage_dir or tempfile.gettempdir()
        self._stored: dict[str, StoredResult] = {}
        self._replacement_state = ContentReplacementState()

    def should_externalize(self, content: str) -> bool:
        return len(content) > self._max_inline_chars

    def make_pointer(self, path: str, original_size: int, preview: str) -> str:
        return (
            f"{PERSISTED_OUTPUT_TAG}\n"
            f"path={path}\n"
            f"original_size={original_size}\n"
            f"preview={preview}"
        )

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _externalize(self, tool_use_id: str, content: str) -> tuple[str, StoredResult]:
        """Write content to disk, record the pointer, and return both."""
        path = os.path.join(self._storage_dir, f"result_{tool_use_id}.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        preview = preview_result(content, limit=PREVIEW_CHARS)
        stored = StoredResult(
            tool_use_id=tool_use_id,
            path=path,
            original_size=len(content),
            preview=preview,
        )
        self._stored[tool_use_id] = stored
        pointer = self.make_pointer(path, len(content), preview)
        self._replacement_state.record(tool_use_id, pointer)
        return pointer, stored

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_result(
        self, tool_use_id: str, content: str
    ) -> tuple[str, StoredResult | None]:
        """Externalize content if over the per-item threshold; otherwise return as-is.

        Checks ContentReplacementState first: once a tool_use_id has been
        externalized, the cached pointer is always returned regardless of the
        content passed in (ensures prompt-cache stability across context rebuilds).

        Returns:
            (out_content, stored) — stored is None when not externalized.
        """
        if self._replacement_state.has_replacement(tool_use_id):
            stored = self._stored.get(tool_use_id)
            pointer = self._replacement_state.get_replacement(tool_use_id)
            if stored is not None and pointer is not None:
                return pointer, stored
            # State inconsistency (replacement recorded without _stored entry) —
            # fall through to re-externalize and repair both caches.
        if not self.should_externalize(content):
            return content, None
        return self._externalize(tool_use_id, content)

    def process_results_batch(
        self,
        results: list[tuple[str, str]],
    ) -> list[tuple[str, StoredResult | None]]:
        """Process a batch of tool results with per-item and total-budget checks.

        Pass 1 — per-item threshold:
            Any result whose content exceeds max_inline_chars is externalized.
            ContentReplacementState idempotency applies here too.

        Pass 2 — total budget:
            If the sum of remaining inline content exceeds total_budget_chars,
            the largest inline items are externalized one by one (largest first)
            until the total drops to or below the budget.

        Returns a list of (out_content, StoredResult | None) in the same order
        as the input.
        """
        if not results:
            return []

        outputs: list[tuple[str, StoredResult | None]] = []
        inline_indices: list[int] = []

        for i, (tool_use_id, content) in enumerate(results):
            out, stored = self.process_result(tool_use_id, content)
            outputs.append((out, stored))
            if stored is None:
                inline_indices.append(i)

        total_inline = sum(len(results[i][1]) for i in inline_indices)
        if total_inline > self._total_budget_chars:
            inline_indices.sort(key=lambda i: len(results[i][1]), reverse=True)
            for i in inline_indices:
                if total_inline <= self._total_budget_chars:
                    break
                tool_use_id, content = results[i]
                # Check cache first: a duplicate tool_use_id in the batch may
                # have been externalized earlier in this same pass.
                if self._replacement_state.has_replacement(tool_use_id):
                    pointer = self._replacement_state.get_replacement(tool_use_id)
                    stored = self._stored.get(tool_use_id)
                    if pointer is None or stored is None:
                        pointer, stored = self._externalize(tool_use_id, content)
                else:
                    pointer, stored = self._externalize(tool_use_id, content)
                outputs[i] = (pointer, stored)
                total_inline -= len(content)

        return outputs

    def retrieve(self, tool_use_id: str) -> str | None:
        """Read the full content for a previously externalized result."""
        stored = self._stored.get(tool_use_id)
        if stored is None:
            return None
        with open(stored.path, encoding="utf-8") as fh:
            return fh.read()
