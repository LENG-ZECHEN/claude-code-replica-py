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
import logging
import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Protocol

from .context import ContextBudget, _estimate_messages_tokens, _normalize_messages
from .models import (
    CompactSummary,
    FileSnapshot,
    Message,
    MessageType,
    Role,
    ToolCall,
    ToolResult,
)
from .provider import PromptTooLongError, Provider
from .trace import NullTracer, Tracer
from .transcript import Transcript

logger = logging.getLogger(__name__)

_DEFAULT_SUMMARY_MAX_RESULT_CHARS = 200
COMPACTABLE_TOOLS = frozenset({
    "read_file",
    "run_shell",
    "search_text",
    "list_files",
})
CLEARED_TOOL_RESULT_CONTENT = "[Old tool result content cleared]"
_SUMMARY_TAG_RE = re.compile(
    r"<summary>\s*(?P<summary>.*?)\s*</summary>",
    re.DOTALL | re.IGNORECASE,
)

_DEFAULT_LLM_MAX_INPUT_TOKENS = 100_000
_KEEP_RECENT_ON_TRUNCATE = 20

TEMPLATE_HEAD = (
    "Your task is to create a detailed summary of the conversation so far, "
    "paying close attention to the user's explicit requests and the prior "
    "actions taken. This summary will replace the older portion of the "
    "transcript, so it must be thorough enough to continue the work without "
    "re-reading the evicted messages.\n\n"
    "Produce your final answer inside <summary>...</summary> tags. The "
    "summary must contain the following nine numbered sections, in order, "
    "each on its own line, with the exact headings shown:\n\n"
    "1. Primary Request and Intent: Capture every explicit request and "
    "intent the user has expressed, including constraints, acceptance "
    "criteria, and scope boundaries.\n"
    "2. Key Technical Concepts: List the important technologies, "
    "frameworks, languages, and patterns discussed.\n"
    "3. Files and Code Sections: Enumerate specific files and code "
    "sections examined, created, or modified. Include the file paths and "
    "the specific code being modified (function names, class names, line "
    "ranges) so work can resume without re-reading.\n"
    "4. Errors and fixes: List the errors encountered and how each was "
    "resolved (or that it is still open).\n"
    "5. Problem Solving: Document the problems solved and any ongoing "
    "troubleshooting still in flight.\n"
    "6. All user messages: List every non-tool user message verbatim, in "
    "order, numbered [1], [2], [3] ... This section is critical for "
    "tracking user feedback and changes of intent.\n"
    "7. Pending Tasks: List the tasks the user has explicitly asked to be "
    "worked on that are not yet complete.\n"
    "8. Current Work: Describe precisely what was being worked on "
    "immediately before this summary was requested -- the function, file, "
    "test, or debug step in progress.\n"
    "9. Optional Next Step: State the single next step that continues the "
    "current work, or \"(none)\" if no next step is implied.\n\n"
    "Here is the conversation to summarize:\n\n"
)

TEMPLATE_TAIL = (
    "\n\nProvide the summary now, inside <summary>...</summary> tags, "
    "following the nine-section structure above."
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
    """Provider-backed Summarizer with input-token control and graceful fallback.

    Behavior:
      * Pre-truncates messages when serialized input exceeds ``max_input_tokens``
        by keeping the first user message plus the most recent
        ``_KEEP_RECENT_ON_TRUNCATE`` messages. If the first user message is
        already inside the recent slice it is not re-prepended (preserves
        ordering, avoids duplicates).
      * Builds the user prompt by concatenating ``TEMPLATE_HEAD`` + a JSON
        dump of the (possibly truncated) transcript + ``TEMPLATE_TAIL``.
        Concatenation is used instead of ``str.format`` because the JSON dump
        contains literal ``{`` / ``}`` characters that would break ``format``.
      * Calls the injected provider and extracts ``<summary>...</summary>``.
      * Falls back to ``fallback_summarizer`` (default ``RuleBasedSummarizer``)
        on empty response, missing tags, empty tags, or any non-PromptTooLong
        provider exception. A warning is logged on the exception path.
      * Re-raises ``PromptTooLongError`` so the caller (e.g. AgentLoop) can
        decide on its own retry/compaction policy.

    ContextCompactor still defaults to ``RuleBasedSummarizer`` -- this class
    is opt-in via ``ContextCompactor(summarizer=LLMSummarizer(provider))``.
    """

    def __init__(
        self,
        provider: Provider,
        *,
        max_input_tokens: int = _DEFAULT_LLM_MAX_INPUT_TOKENS,
        fallback_summarizer: Summarizer | None = None,
    ) -> None:
        self.provider = provider
        self.max_input_tokens = max_input_tokens
        self.fallback_summarizer = fallback_summarizer or RuleBasedSummarizer()

    def summarize(self, messages: list[Message]) -> str:
        if not messages:
            return ""

        truncated = self._truncate_if_oversized(messages)
        json_str = json.dumps(_normalize_messages(truncated), indent=2)
        user_prompt = TEMPLATE_HEAD + json_str + TEMPLATE_TAIL
        system = (
            "You summarize compacted coding-agent transcripts. "
            "Always return your final answer inside <summary>...</summary> tags."
        )

        try:
            response = self.provider.call(
                system=system,
                messages=[{"role": "user", "content": user_prompt}],
                tools=[],
            )
        except PromptTooLongError:
            raise
        except Exception as exc:
            logger.warning(
                "LLMSummarizer provider call failed (%s); falling back to %s",
                exc.__class__.__name__,
                self.fallback_summarizer.__class__.__name__,
            )
            return self.fallback_summarizer.summarize(messages)

        text = response.text or ""
        if not text:
            return self.fallback_summarizer.summarize(messages)

        match = _SUMMARY_TAG_RE.search(text)
        if match is None:
            return self.fallback_summarizer.summarize(messages)

        extracted = match.group("summary").strip()
        if not extracted:
            return self.fallback_summarizer.summarize(messages)
        return extracted

    def _truncate_if_oversized(self, messages: list[Message]) -> list[Message]:
        """Drop middle messages when serialized input exceeds the token cap.

        Keeps the first user message plus the most recent
        ``_KEEP_RECENT_ON_TRUNCATE`` messages. If the first user message is
        already within the recent slice (or there is no user message at all),
        it is NOT prepended again so message order is preserved and no
        duplicate is created.
        """
        estimate = ContextBudget.estimate_tokens(
            json.dumps(_normalize_messages(messages))
        )
        if estimate <= self.max_input_tokens:
            return messages

        first_user_idx = next(
            (i for i, m in enumerate(messages) if m.role == Role.USER),
            None,
        )
        recent = messages[-_KEEP_RECENT_ON_TRUNCATE:]
        if (
            first_user_idx is None
            or first_user_idx >= len(messages) - _KEEP_RECENT_ON_TRUNCATE
        ):
            result = recent
        else:
            result = [messages[first_user_idx], *recent]
        logger.info(
            "LLMSummarizer truncated %d messages -> %d",
            len(messages),
            len(result),
        )
        return result


_DEFAULT_MICROCOMPACT_MINUTES = 60
_DEFAULT_MICROCOMPACT_KEEP_RECENT = 5


class MicroCompactor:
    """Cold-cache cleanup for old compactable tool results.

    keep_recent: the N most recent compactable tool_results are preserved
      untouched; only older ones are cleared. Source: PDF §3 microcompact
      "keep latest 5". keep_recent=0 reproduces the pre-PDF clear-everything
      behaviour.
    """

    def __init__(
        self,
        *,
        threshold_minutes: int = _DEFAULT_MICROCOMPACT_MINUTES,
        keep_recent: int = _DEFAULT_MICROCOMPACT_KEEP_RECENT,
        tracer: Tracer | None = None,
    ) -> None:
        if threshold_minutes < 0:
            raise ValueError("threshold_minutes must be >= 0")
        if keep_recent < 0:
            raise ValueError("keep_recent must be >= 0")
        self._threshold_minutes = threshold_minutes
        self._keep_recent = keep_recent
        self._tracer: Tracer = tracer or NullTracer()

    def should_microcompact(
        self,
        messages: list[Message],
        threshold_minutes: int | None = None,
        now: datetime | None = None,
    ) -> bool:
        effective_threshold = (
            threshold_minutes
            if threshold_minutes is not None
            else self._threshold_minutes
        )
        if not messages:
            return False

        current_time = now or datetime.now(UTC)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=UTC)

        latest_assistant_time: datetime | None = None
        for msg in messages:
            if msg.role != Role.ASSISTANT:
                continue
            timestamp = self._parse_timestamp(msg.timestamp)
            if timestamp is None:
                continue
            if latest_assistant_time is None or timestamp > latest_assistant_time:
                latest_assistant_time = timestamp

        if latest_assistant_time is None:
            return True

        return current_time - latest_assistant_time > timedelta(minutes=effective_threshold)

    def microcompact(self, messages: list[Message]) -> list[Message]:
        tool_names_by_id = self._tool_names_by_id(messages)
        preserved = self._recent_compactable_positions(messages, tool_names_by_id)
        compacted: list[Message] = []
        cleared = 0

        for msg_index, msg in enumerate(messages):
            if not isinstance(msg.content, list):
                compacted.append(replace(msg))
                continue

            new_content: list[ToolCall | ToolResult] = []
            for item_index, item in enumerate(msg.content):
                if isinstance(item, ToolCall):
                    new_content.append(replace(item, input=dict(item.input)))
                    continue
                tool_name = tool_names_by_id.get(item.tool_use_id)
                if (
                    tool_name in COMPACTABLE_TOOLS
                    and (msg_index, item_index) not in preserved
                ):
                    new_content.append(replace(
                        item,
                        content=CLEARED_TOOL_RESULT_CONTENT,
                    ))
                    cleared += 1
                else:
                    new_content.append(replace(item))
            compacted.append(replace(msg, content=new_content))

        self._tracer.emit(
            "microcompact",
            cleared=cleared,
            messages=len(compacted),
        )
        return compacted

    def _recent_compactable_positions(
        self,
        messages: list[Message],
        tool_names_by_id: dict[str, str | None],
    ) -> set[tuple[int, int]]:
        """Return (msg_index, item_index) of the keep_recent newest results.

        Compactable tool_results are collected in transcript order; the last
        ``keep_recent`` of them are preserved (not cleared). keep_recent=0
        preserves none, reproducing the pre-PDF clear-everything behaviour.
        """
        if self._keep_recent == 0:
            return set()
        positions: list[tuple[int, int]] = []
        for msg_index, msg in enumerate(messages):
            if not isinstance(msg.content, list):
                continue
            for item_index, item in enumerate(msg.content):
                if (
                    isinstance(item, ToolResult)
                    and tool_names_by_id.get(item.tool_use_id) in COMPACTABLE_TOOLS
                ):
                    positions.append((msg_index, item_index))
        return set(positions[-self._keep_recent:])

    @staticmethod
    def _parse_timestamp(value: str) -> datetime | None:
        if not value:
            return None
        try:
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def _tool_names_by_id(messages: list[Message]) -> dict[str, str | None]:
        tool_names: dict[str, str | None] = {}
        for msg in messages:
            if msg.role != Role.ASSISTANT or not isinstance(msg.content, list):
                continue
            for item in msg.content:
                if not isinstance(item, ToolCall):
                    continue
                existing = tool_names.get(item.id)
                if existing is None and item.id not in tool_names:
                    tool_names[item.id] = item.name
                elif existing != item.name:
                    tool_names[item.id] = None
        return tool_names


_DEFAULT_OUTPUT_HEADROOM = 12_000
_DEFAULT_COMPACT_HEADROOM = 20_000
_DEFAULT_MIN_SESSION_TOKENS = 30_000


class ContextCompactor:
    """Decides when to compact and produces a CompactSummary.

    compact_threshold: fraction of budget.available_tokens above which the
      legacy ratio trigger fires. Preserved as a SECOND trigger alongside the
      PDF double-headroom formula (the aggressive-thresholds preset lowers it).
    keep_recent: messages re-appended after the boundary marker.
    summary_max_result_chars: tool result content is truncated to this length
      in the summary to avoid bloating.

    PDF §4 autoCompact threshold (new primary trigger): compaction fires when
      used >= context_window - output_headroom - compact_headroom
      AND used >= min_session_tokens, where context_window maps to
      budget.max_tokens. should_compact() returns True if EITHER this formula
      OR the legacy ratio fires.

    summarizer selection: an explicit ``summarizer`` always wins; otherwise a
      supplied ``provider`` selects ``LLMSummarizer`` (PDF §4 "LLM-based"
      default); with neither, ``RuleBasedSummarizer`` is used (backward compat).
    """

    def __init__(
        self,
        keep_recent: int = 10,
        compact_threshold: float = 0.8,
        summary_max_result_chars: int = _DEFAULT_SUMMARY_MAX_RESULT_CHARS,
        summarizer: Summarizer | None = None,
        *,
        output_headroom: int = _DEFAULT_OUTPUT_HEADROOM,
        compact_headroom: int = _DEFAULT_COMPACT_HEADROOM,
        min_session_tokens: int = _DEFAULT_MIN_SESSION_TOKENS,
        provider: Provider | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self.keep_recent = keep_recent
        self.compact_threshold = compact_threshold
        self.summary_max_result_chars = summary_max_result_chars
        self.output_headroom = output_headroom
        self.compact_headroom = compact_headroom
        self.min_session_tokens = min_session_tokens
        if summarizer is not None:
            self.summarizer: Summarizer = summarizer
        elif provider is not None:
            self.summarizer = LLMSummarizer(provider)
        else:
            self.summarizer = RuleBasedSummarizer(
                summary_max_result_chars=summary_max_result_chars,
            )
        self._tracer: Tracer = tracer or NullTracer()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def should_compact(self, transcript: Transcript, budget: ContextBudget) -> bool:
        """True when either the PDF formula or the legacy ratio trigger fires.

        Primary (PDF §4): used >= context_window - output_headroom
          - compact_headroom AND used >= min_session_tokens, with
          context_window = budget.max_tokens.
        Legacy (preserved 2nd trigger): used > available_tokens * threshold.
        """
        messages = transcript.messages_after_compact_boundary()
        if not messages:
            return False
        api_messages = _normalize_messages(messages)
        used = _estimate_messages_tokens(api_messages)

        formula_threshold = (
            budget.max_tokens - self.output_headroom - self.compact_headroom
        )
        formula_fires = (
            used >= formula_threshold and used >= self.min_session_tokens
        )

        legacy_threshold = int(budget.available_tokens * self.compact_threshold)
        legacy_fires = used > legacy_threshold

        return formula_fires or legacy_fires

    def compact(
        self,
        transcript: Transcript,
        budget: ContextBudget,
        *,
        snapshots: tuple[FileSnapshot, ...] = (),
    ) -> CompactSummary:
        """Summarize old messages, append boundary + kept messages, return summary.

        Source: compactConversation() in src/services/compact/compact.ts.
        After this call, transcript.messages_after_compact_boundary() returns
        [boundary_marker, *to_keep] so ContextBuilder sees the recent turns.

        ``snapshots`` (M3) are the recent FileSnapshots captured before this
        compaction; they are stored verbatim on the returned CompactSummary so
        ContextBuilder.build() can re-attach them as ATTACHMENT messages.
        """
        recent_file_snapshots = tuple(snapshots)
        current = transcript.messages_after_compact_boundary()
        n = len(current)

        if n == 0:
            boundary = Message.compact_boundary()
            transcript.append(boundary)
            self._tracer.emit(
                "compact",
                messages=0,
                post_tokens=0,
                pre_tokens=0,
                summarized=0,
            )
            return CompactSummary(
                boundary_uuid=boundary.uuid,
                summary_text="",
                messages_summarized=0,
                pre_token_count=0,
                post_token_count=0,
                recent_file_snapshots=recent_file_snapshots,
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

        self._tracer.emit(
            "compact",
            messages=n,
            post_tokens=post_tokens,
            pre_tokens=pre_tokens,
            summarized=len(to_summarize),
        )
        return CompactSummary(
            boundary_uuid=boundary.uuid,
            summary_text=summary_text,
            messages_summarized=len(to_summarize),
            pre_token_count=pre_tokens,
            post_token_count=post_tokens,
            recent_file_snapshots=recent_file_snapshots,
        )

    def _summarize(self, messages: list[Message]) -> str:
        """Compatibility shim for callers that used the old private method."""
        return self.summarizer.summarize(messages)
