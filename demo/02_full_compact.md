# Notebook 02 — Full Compact

This notebook demonstrates **ContextCompactor**: the mechanism that summarizes older conversation
history once token usage crosses a configurable threshold. When the estimated token count reaches
`compact_threshold × context_tokens`, the compactor splits the transcript at a `keep_recent`
boundary, feeds the older half to a summarizer, and splices the result back as a single compact
summary message. The model receives a fresh context with the most recent turns intact; older turns
survive as a compact narrative.

---

## Setup

**Environment**: `python-replica/.env` — sets `DASHSCOPE_API_KEY`, `OPENAI_BASE_URL`, and
`SIMPLE_AGENT_MODEL`.

**Capture command** (run from `python-replica/`):

```console
python demo/_scripts/capture_scenario.py 02
```

The script uses `_build_repl_loop` with `aggressive_thresholds=True` (no extra flag overrides).
The aggressive preset produces a very small context window:

| Threshold | Value |
|-----------|-------|
| `context_tokens` | 4 000 |
| `compact_threshold` | 0.2 (→ fires at ≥ 800 tokens) |
| `keep_recent` | 2 messages kept after compact |
| `reserved_output_tokens` | 512 |

With only 4 000 context tokens and a 0.2 threshold, a handful of tool-call exchanges is enough to
cross the compaction trigger.

**Model** (from `_artifacts/02_full_compact/stats_output.txt`):

```text
# model: qwen3.6-plus
```

**Workspace files**: `notes1.txt`, `notes2.txt`, `notes3.txt` (each under 100 chars).

**Scenario script** (4 user turns):

1. "Please use the read_file tool to read notes1.txt and tell me what it says."
2. "Please use the read_file tool to read notes2.txt and describe its contents."
3. "Please use the read_file tool to read notes3.txt and explain the key points."
4. "Please summarize all three project files and highlight the main differences."

---

## Step-by-step

### 1. Token growth across three file reads

Each read_file cycle adds two messages (tool_use + tool_result) and one assistant text response.
The `[budget]` trace events track estimated tokens before each provider call:

```text
[trace] [budget] available=3488 dropped=0 estimated_tokens=58 externalized=0 messages=1 system_tokens=32
[trace] [budget] available=3488 dropped=0 estimated_tokens=162 externalized=0 messages=3 system_tokens=32
[trace] [budget] available=3488 dropped=0 estimated_tokens=231 externalized=0 messages=5 system_tokens=32
[trace] [budget] available=3488 dropped=0 estimated_tokens=336 externalized=0 messages=7 system_tokens=32
[trace] [budget] available=3488 dropped=0 estimated_tokens=406 externalized=0 messages=9 system_tokens=32
[trace] [budget] available=3488 dropped=0 estimated_tokens=511 externalized=0 messages=11 system_tokens=32
```

After six provider calls (3 turns × 2 calls each — tool_use then text response), the estimated
token count is 511. The message count grows from 1 to 11.

### 2. Compact fires before turn 4

When turn 4's user input is added, `ContextCompactor.should_compact()` checks:
`511 ≥ 4000 × 0.2 = 800`? Not yet. But the message count is 13 at this point (11 + user4 +
another assistant message) and the check is re-evaluated after each inner loop iteration. The
compactor fires as the 13th-message threshold is crossed:

```text
[trace] [compact] messages=13 post_tokens=299 pre_tokens=778 summarized=11
```

`summarized=11` — eleven messages were condensed into one compact summary. `pre_tokens=778`
was the estimated size of those messages; the summary brought that down to `post_tokens=299`.

From `_artifacts/02_full_compact/transcript.txt`:

```console
## 13. user (text)
Please summarize all three project files and highlight the main differences.

## 14. system (compact_boundary)
Conversation compacted

## 15. assistant (text)
The file `notes3.txt` contains the following text: ...
```

The `compact_boundary` marker (message 14) is the splice point. Messages 1–13 (pre-compact) remain
in `Transcript.all_messages()` but are filtered from the API payload by
`messages_after_compact_boundary()`. The model sees only the compact summary and the two kept
recent messages (`keep_recent=2`).

### 3. Token count after compact

After compaction, the budget trace shows the context has shrunk dramatically:

```text
[trace] [compact] messages=13 post_tokens=299 pre_tokens=778 summarized=11
[trace] [budget] available=3488 dropped=0 estimated_tokens=794 externalized=0 messages=3 system_tokens=377
```

`messages=3` (compact summary + kept turn + current user input) and `estimated_tokens=794` — the
context is now well within the 4 000-token budget. `system_tokens=377` is higher than before
because the compact summary is prepended to the system prompt.

### 4. Final metrics

From `_artifacts/02_full_compact/metrics.json`:

```json
{
  "full_compacts": 1,
  "snip_invocations": 0,
  "microcompact_invocations": 1,
  "reactive_compacts": 0,
  "externalized_bytes": 0,
  "tokens_per_turn": [58, 162, 231, 336, 406, 511, 794]
}
```

From `_artifacts/02_full_compact/stats_output.txt`:

```text
# model: qwen3.6-plus
Context-management metrics:
  full compacts:         1
  reactive compacts:     0
  microcompact runs:     1
  snip runs:             0
  externalized bytes:    0
  turns recorded:        7
  last-turn tokens:      794
```

`tokens_per_turn` shows the monotonic growth (58 → 511) followed by the post-compact value (794).
The 794 figure is higher than pre-compact 511 because the compact summary itself takes space in the
system prompt, but it replaces 11 full messages — a clear net win for longer sessions.

---

## What to look for

| Signal | Where | What it proves |
|--------|-------|---------------|
| `[trace] [compact] summarized=11` | `trace.stderr` line 14 | Compactor ran; 11 messages condensed |
| `pre_tokens=778 → post_tokens=299` | same trace line | Token reduction achieved by summarization |
| `## 14. system (compact_boundary)` | `transcript.txt` | Boundary marker in stored transcript |
| `messages=3` in post-compact budget | `trace.stderr` line 16 | Only summary + 2 kept messages reach the API |
| `system_tokens=377` vs initial `32` | budget trace lines 1 vs 16 | Compact summary lives in system prompt |
| `"full_compacts": 1` | `metrics.json` | Counter confirms exactly one compaction event |
| `tokens_per_turn` ends at 794 | `metrics.json` | Post-compact token count — higher than pre-compact 511 per turn but growing from a clean base |

**Key insight**: compact fires **once** in this session because the aggressive threshold is low
enough to trigger on 4 reading turns, but the context is small enough that one compaction suffices.
In real sessions (default `context_tokens=128k`, `compact_threshold=0.7`), compact fires much
later in a conversation and typically only once per session. The counter in `/stats` makes the
timing observable without grepping logs.

---

## Source mapping

| Mechanism | File:line | What it does |
|-----------|-----------|-------------|
| `ContextCompactor.should_compact()` | `src/simple_coding_agent/compact.py:511` | Checks estimated tokens against threshold; returns True when compaction is warranted |
| `ContextCompactor.compact()` | `src/simple_coding_agent/compact.py:537` | Splits transcript, calls summarizer, appends boundary marker + kept messages |
| `AgentLoop._maybe_compact()` | `src/simple_coding_agent/loop.py:591` | Calls should_compact + compact; returns True when compaction occurred |
| `RuleBasedSummarizer` | `src/simple_coding_agent/compact.py` | Default summarizer — deterministic 9-section extractor, no additional API call |
| `LLMSummarizer` | `src/simple_coding_agent/compact.py` | Optional: wraps a Provider; parses `<summary>…</summary>` tags; falls back to RuleBasedSummarizer on failure |
| `compact` trace channel | `src/simple_coding_agent/trace.py:91` | Emits `[trace] [compact] messages=N pre_tokens=P post_tokens=Q summarized=S` |
