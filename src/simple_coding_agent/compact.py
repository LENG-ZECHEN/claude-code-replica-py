"""
ContextCompactor: transcript summarization and compaction.

Source mapping:
  ContextCompactor.should_compact <- autocompact threshold check in src/query.ts
  ContextCompactor.compact        <- compactConversation() in src/services/compact/compact.ts
  Summarizer                      <- compact prompt provider boundary in
                                     src/services/compact/compact.ts
  RuleBasedSummarizer             <- BASE_COMPACT_PROMPT 9-section format in
                                     src/services/compact/prompt.ts
  keep_recent                     <- messagesToKeep in CompactionResult
  compact_threshold               <- (usedTokens >= effectiveContextWindow - 13_000)
                                     simplified to fraction of available_tokens

Note: the source uses an LLM to generate the summary.  This replica defaults to
a deterministic rule-based extractor so tests are fast and reproducible, while
allowing an opt-in provider-backed summarizer.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Protocol

from .context import ContextBudget, _estimate_messages_tokens, _normalize_messages
from .models import CompactSummary, Message, MessageType, Role, ToolCall, ToolResult
from .transcript import Transcript

if TYPE_CHECKING:
    from .provider import Provider

_DEFAULT_SUMMARY_MAX_RESULT_CHARS = 200
_SUMMARY_TAG_RE = re.compile(
    r"<summary>\s*(?P<summary>.*?)\s*</summary>",
    re.DOTALL | re.IGNORECASE,
)


class Summarizer(Protocol):
    """Transcript summarizer dependency used by ContextCompactor."""

    def summarize(self, messages: list[Message]) -> str:
        """Return a compact summary for the messages being evicted."""
        ...


class RuleBasedSummarizer:
    """Deterministic 9-section summary from a message list.

    Source: BASE_COMPACT_PROMPT section schema in
    src/services/compact/prompt.ts.  The source uses an LLM; here we
    extract content with simple heuristics so tests are deterministic.
    """

    def __init__(
        self,
        summary_max_result_chars: int = _DEFAULT_SUMMARY_MAX_RESULT_CHARS,
    ) -> None:
        self.summary_max_result_chars = summary_max_result_chars

    def summarize(self, messages: list[Message]) -> str:
        if not messages:
            return ""

        user_texts: list[str] = []
        assistant_texts: list[str] = []
        tool_calls_seen: list[str] = []
        tool_results_seen: list[str] = []
        error_notes: list[str] = []

        for msg in messages:
            if msg.is_virtual:
                continue
            if msg.type in (MessageType.COMPACT_BOUNDARY, MessageType.ATTACHMENT):
                continue

            if msg.role == Role.USER and isinstance(msg.content, str):
                user_texts.append(msg.content)
            elif msg.role == Role.ASSISTANT and isinstance(msg.content, str):
                assistant_texts.append(msg.content)
            elif isinstance(msg.content, list):
                for item in msg.content:
                    if isinstance(item, ToolCall):
                        tool_calls_seen.append(
                            f"{item.name}({json.dumps(item.input)})"
                        )
                    elif isinstance(item, ToolResult):
                        preview = item.content[: self.summary_max_result_chars]
                        if len(item.content) > self.summary_max_result_chars:
                            preview += f"... [{len(item.content)} chars total]"
                        if item.is_error:
                            error_notes.append(f"Tool error: {preview}")
                        else:
                            tool_results_seen.append(preview)

        sections: list[str] = [
            "1. Primary Request and Intent:\n" + (
                "\n".join(f"   - {t}" for t in user_texts) or "   (none)"
            ),
            "2. Key Technical Concepts:\n   (extracted from conversation)",
            "3. Files and Code Sections:\n" + (
                "\n".join(f"   - {tc}" for tc in tool_calls_seen) or "   (none)"
            ),
            "4. Errors Encountered:\n" + (
                "\n".join(f"   - {e}" for e in error_notes) or "   (none)"
            ),
            "5. Problem Solving:\n" + (
                "\n".join(f"   - result: {r}" for r in tool_results_seen[:3])
                or "   (none)"
            ),
            "6. All User Messages:\n" + (
                "\n".join(f"   [{i + 1}] {t}" for i, t in enumerate(user_texts))
                or "   (none)"
            ),
            "7. Pending Tasks:\n   (see user messages above)",
            "8. Current Work:\n" + (
                f"   {assistant_texts[-1]}" if assistant_texts else "   (none)"
            ),
            "9. Optional Next Step:\n   (continue from current work)",
        ]

        return "\n\n".join(sections)


class LLMSummarizer:
    """Provider-backed Summarizer for opt-in compaction experiments.

    Tests pass a fake provider.  Production callers can supply any object that
    implements Provider, but ContextCompactor still defaults to RuleBasedSummarizer
    to keep the safe offline path unchanged.
    """

    def __init__(self, provider: Provider) -> None:
        self.provider = provider

    def summarize(self, messages: list[Message]) -> str:
        if not messages:
            return ""

        system = (
            "You summarize compacted coding-agent transcripts. "
            "Preserve user intent, current work, tool outcomes, errors, and "
            "next steps. Return the result inside <summary>...</summary> tags."
        )
        user_prompt = (
            "Summarize these messages for future context. "
            "Be concise but keep details needed to continue the work.\n\n"
            f"{json.dumps(_normalize_messages(messages), indent=2)}"
        )
        response = self.provider.call(
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
            tools=[],
        )
        text = response.text or ""
        match = _SUMMARY_TAG_RE.search(text)
        if match is None:
            return text
        return match.group("summary").strip()


class ContextCompactor:
    """Decides when to compact and produces a CompactSummary.

    compact_threshold: fraction of budget.available_tokens above which
      should_compact() returns True.
    keep_recent: messages re-appended after the boundary marker.
    summary_max_result_chars: tool result content is truncated to this length
      in the summary to avoid bloating.
    """

    def __init__(
        self,
        keep_recent: int = 10,
        compact_threshold: float = 0.8,
        summary_max_result_chars: int = _DEFAULT_SUMMARY_MAX_RESULT_CHARS,
        summarizer: Summarizer | None = None,
    ) -> None:
        self.keep_recent = keep_recent
        self.compact_threshold = compact_threshold
        self.summary_max_result_chars = summary_max_result_chars
        self.summarizer = summarizer or RuleBasedSummarizer(
            summary_max_result_chars=summary_max_result_chars,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def should_compact(self, transcript: Transcript, budget: ContextBudget) -> bool:
        """True when message tokens exceed compact_threshold * available_tokens."""
        messages = transcript.messages_after_compact_boundary()
        if not messages:
            return False
        api_messages = _normalize_messages(messages)
        used = _estimate_messages_tokens(api_messages)
        threshold = int(budget.available_tokens * self.compact_threshold)
        return used > threshold

    def compact(self, transcript: Transcript, budget: ContextBudget) -> CompactSummary:
        """Summarize old messages, append boundary + kept messages, return summary.

        Source: compactConversation() in src/services/compact/compact.ts.
        After this call, transcript.messages_after_compact_boundary() returns
        [boundary_marker, *to_keep] so ContextBuilder sees the recent turns.
        """
        current = transcript.messages_after_compact_boundary()
        n = len(current)

        if n == 0:
            boundary = Message.compact_boundary()
            transcript.append(boundary)
            return CompactSummary(
                boundary_uuid=boundary.uuid,
                summary_text="",
                messages_summarized=0,
                pre_token_count=0,
                post_token_count=0,
            )

        split = max(0, n - self.keep_recent)
        to_summarize = current[:split]
        to_keep = current[split:]

        summary_text = self.summarizer.summarize(to_summarize)

        pre_tokens = _estimate_messages_tokens(_normalize_messages(current))
        post_tokens = _estimate_messages_tokens(_normalize_messages(to_keep))

        boundary = Message.compact_boundary(messages_summarized=len(to_summarize))
        transcript.append(boundary)

        for msg in to_keep:
            transcript.append(msg)

        return CompactSummary(
            boundary_uuid=boundary.uuid,
            summary_text=summary_text,
            messages_summarized=len(to_summarize),
            pre_token_count=pre_tokens,
            post_token_count=post_tokens,
        )

    def _summarize(self, messages: list[Message]) -> str:
        """Compatibility shim for callers that used the old private method."""
        return self.summarizer.summarize(messages)
