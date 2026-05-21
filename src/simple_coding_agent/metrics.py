"""
MetricsCollector: per-loop counters for context-management mechanisms.

Source mapping:
  MetricsCollector  <- distilled from telemetry events in queryLoop()
                       (compact-fired / microcompact-fired / snip-fired /
                        reactive-compact / persisted-output emitted on every
                        turn in src/query.ts and src/services/compact/*).

Each `AgentLoop` instance owns one `MetricsCollector`; the loop bumps each
counter at the precise fire site of the corresponding mechanism so the REPL
`/stats` command (and the M3 demos) can prove the mechanism actually ran.

The collector is intentionally a plain mutable dataclass — counters are
write-once-per-event, and the `AgentLoop` is the only writer. Callers read
counters directly (`metrics.full_compacts`, etc.) rather than going through
accessor methods.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MetricsCollector:
    """Per-loop counters for context-management mechanisms.

    Fields:
      full_compacts             -- ContextCompactor.compact() invocations
                                   (covers both threshold and reactive paths)
      snip_invocations          -- SnipTool.snip() invocations
      microcompact_invocations  -- MicroCompactor.microcompact() invocations
      reactive_compacts         -- PromptTooLongError-driven retries that
                                   triggered an additional force-compact
      externalized_bytes        -- total bytes a ToolResultStore wrote to disk
                                   for this loop's tool results
      tokens_per_turn           -- BuiltContext.estimated_tokens per AgentStep
                                   (one entry per appended step, including
                                   max-tokens partials)
    """

    full_compacts: int = 0
    snip_invocations: int = 0
    microcompact_invocations: int = 0
    reactive_compacts: int = 0
    externalized_bytes: int = 0
    tokens_per_turn: list[int] = field(default_factory=list)

    def record_full_compact(self) -> None:
        self.full_compacts += 1

    def record_snip(self) -> None:
        self.snip_invocations += 1

    def record_microcompact(self) -> None:
        self.microcompact_invocations += 1

    def record_reactive_compact(self) -> None:
        self.reactive_compacts += 1

    def add_externalized_bytes(self, byte_count: int) -> None:
        if byte_count < 0:
            raise ValueError(f"byte_count must be >= 0, got {byte_count}")
        self.externalized_bytes += byte_count

    def record_turn_tokens(self, token_estimate: int) -> None:
        if token_estimate < 0:
            raise ValueError(
                f"token_estimate must be >= 0, got {token_estimate}",
            )
        self.tokens_per_turn.append(token_estimate)

    def format_stats(self) -> str:
        """Render a multi-line human-readable summary (used by REPL /stats)."""
        lines = [
            "Context-management metrics:",
            f"  full compacts:         {self.full_compacts}",
            f"  reactive compacts:     {self.reactive_compacts}",
            f"  microcompact runs:     {self.microcompact_invocations}",
            f"  snip runs:             {self.snip_invocations}",
            f"  externalized bytes:    {self.externalized_bytes}",
            f"  turns recorded:        {len(self.tokens_per_turn)}",
        ]
        if self.tokens_per_turn:
            last = self.tokens_per_turn[-1]
            lines.append(f"  last-turn tokens:      {last}")
        return "\n".join(lines)


__all__ = ["MetricsCollector"]
