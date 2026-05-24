# Notebook 01 — Tool Result Management: Snip + Externalize

This notebook walks through how the agent handles redundant and oversized tool results in a
real API session. Two mechanisms fire in sequence: **SnipTool** folds earlier reads of the same
file once a path has been read three times, and **ToolResultStore** externalizes large results to
disk (replacing them in-context with a compact pointer). Both mechanisms reduce context pressure
without losing information that the model still needs.

---

## Setup

**Environment**: `python-replica/.env` — sets `DASHSCOPE_API_KEY`, `OPENAI_BASE_URL`, and
`SIMPLE_AGENT_MODEL`.

**Capture command** (run from `python-replica/`):

```console
python demo/_scripts/capture_scenario.py 01
```

The script uses `_build_repl_loop` with `aggressive_thresholds=True` and
`microcompact_minutes=60`. The aggressive preset sets `max_inline_chars=2000` (externalize
threshold) and `compact_threshold=0.2` on a `context_tokens=4000` window. `microcompact_minutes=60`
prevents microcompact from interfering — qwen3.6-plus in thinking mode takes ~60 s per call, and
without this override the aggressive preset's 1-minute threshold would fire.

**Model** (from `_artifacts/01_tool_result_management/stats_output.txt`):

```text
# model: qwen3.6-plus
```

**Workspace files**: `small.txt` (280 chars) and `large.txt` (3 800 chars of repeated
`"context token data "`).

**Scenario script** (4 user turns):

1. "Please use the read_file tool to read small.txt and summarize it."
2. "Please use the read_file tool to read small.txt again to verify."
3. "Please use the read_file tool to read small.txt one more time and check for changes."
4. "Please use the read_file tool to read large.txt and give an overview."

---

## Step-by-step

### 1. Three reads of small.txt — snip threshold reached

The first three turns each produce a `read_file(small.txt)` call. After the third read,
`SnipTool.should_snip()` crosses `_PATH_THRESHOLD=3` for that path and `snip()` replaces the
two older results with the sentinel `[Snipped: superseded by later call]`.

Relevant transcript excerpt (from `_artifacts/01_tool_result_management/transcript.txt`):

```console
## 3. user (tool_result)
tool_result: [Snipped: superseded by later call]

## 7. user (tool_result)
tool_result: [Snipped: superseded by later call]

## 11. user (tool_result)
tool_result: Context management design notes: context grows monotonically, tool results older
than keep_recent are snipped, snipping preserves transcript shape while clearing superseded
content. (< 300 chars)
```

The third result (message 11) is kept because it is the most recent read of that path.

Corresponding trace events (from `_artifacts/01_tool_result_management/trace.stderr`):

```text
[trace] [snip] deleted=0 messages=11 snipped=2
[trace] [budget] available=3488 dropped=0 estimated_tokens=629 externalized=0 messages=11 system_tokens=32
```

`snipped=2` confirms two older reads were folded. `deleted=0` means no orphan tool_use blocks
were removed. Token count drops from the pre-snip 575 (turn 5 budget) to 629 after snip — a
modest saving, but the gap grows with more reads.

### 2. Reading large.txt — externalize fires

Turn 4 requests `large.txt`, which is 3 800 chars — above the aggressive preset's
`max_inline_chars=2000`. After the tool result is added to the transcript and context is built,
`ToolResultStore.process_results_batch()` detects the oversized result and externalizes it to a
temp file. The in-context content is replaced by a compact pointer.

Trace event (from `_artifacts/01_tool_result_management/trace.stderr`):

```text
[trace] [externalize] bytes=3800 tool_use_id=call_41d35f98ea5846429098f558
[trace] [budget] available=3488 dropped=0 estimated_tokens=1908 externalized=1 messages=3 system_tokens=240
```

`externalized=1` in the budget line confirms exactly one result is now held outside the context
window. The `bytes=3800` field is the original content size; the in-context replacement is a
short `<persisted-output path=... original_size=3800 preview="..."/>` pointer.

### 3. Full compact fires (twice)

Token pressure from 4 user turns with tool calls crosses the aggressive compact threshold
(`compact_threshold=0.2` of a 4 000-token context = 800 tokens used). The compactor fires before
the large.txt response can reach the model, then fires again as the second compaction attempt:

```text
[trace] [compact] messages=13 post_tokens=112 pre_tokens=709 summarized=11
[trace] [compact] messages=5 post_tokens=1035 pre_tokens=1147 summarized=3
```

The first compact summarizes 11 messages (`pre_tokens=709 → post_tokens=112`); the second
re-compacts the residual context. Together they allow the final response (`estimated_tokens=1908`)
to fit within the 4 000-token budget.

### 4. Final metrics

From `_artifacts/01_tool_result_management/metrics.json`:

```json
{
  "full_compacts": 2,
  "snip_invocations": 2,
  "microcompact_invocations": 1,
  "reactive_compacts": 0,
  "externalized_bytes": 3800,
  "tokens_per_turn": [56, 190, 325, 459, 575, 629, 604, 1908]
}
```

> **Note on `externalized_bytes` (the `/stats` 0 vs `metrics.json` 3800 split)**: These canonical
> artifacts were captured while `_build_repl_loop` had a wiring bug — `ToolResultStore` reached
> `ContextBuilder` but not `AgentLoop`, so `MetricsCollector.externalized_bytes` was never updated
> and `/stats` showed `0`. The capture script worked around it by reading
> `loop._context_builder._store.total_externalized_bytes` directly, which is why `metrics.json`
> shows the real `3800`. **This bug was fixed during the post-execution review**
> (`[ctx-demo/review-fix]` in `cli.py`: the store is now passed to `AgentLoop`, and the capture
> driver's workaround was removed). The artifacts above predate the fix, so they still show the
> 0-vs-3800 split; a fresh re-run now reports `3800` in both `/stats` and `metrics.json`. The
> `[trace] [externalize] bytes=3800` event confirms externalization occurred either way.

From `_artifacts/01_tool_result_management/stats_output.txt`:

```text
# model: qwen3.6-plus
Context-management metrics:
  full compacts:         2
  reactive compacts:     0
  microcompact runs:     1
  snip runs:             2
  externalized bytes:    0
  turns recorded:        8
  last-turn tokens:      1908
```

---

## What to look for

| Signal | Where | What it proves |
|--------|-------|---------------|
| `[trace] [snip] snipped=2` | `trace.stderr` line 12 | SnipTool fired; 2 older small.txt reads folded |
| `[Snipped: superseded by later call]` | `transcript.txt` messages 3, 7 | Folded content replaced with sentinel; transcript shape preserved |
| `[trace] [externalize] bytes=3800` | `trace.stderr` line 20 | large.txt exceeded `max_inline_chars=2000`; result externalized |
| `externalized=1` in budget trace | `trace.stderr` line 22 | Context builder confirms 1 result is held off-context |
| `"snip_invocations": 2` | `metrics.json` | Both snip passes recorded (snip fires once per user turn) |
| `"externalized_bytes": 3800` | `metrics.json` | One result externalized; now flows through `MetricsCollector` after the review-time wiring fix (see note above) |
| `tokens_per_turn` growth then reset | `metrics.json` | Compaction brings token count down between turns 7 and 8 |

**Key insight**: snip and externalize are complementary. Snip removes redundancy within the active
context (same path, older reads). Externalize offloads large payloads to disk when a single result
exceeds the per-item byte cap. Both preserve the model's ability to retrieve the content if needed
(the latest read stays in-context; the externalized result is accessible via `retrieve()`).

---

## Source mapping

| Mechanism | File:line | What it does |
|-----------|-----------|-------------|
| `SnipTool.snip()` | `src/simple_coding_agent/snip.py:169` | Replaces superseded tool results with sentinel; pairs by `tool_use_id` |
| `_PATH_THRESHOLD = 3` | `src/simple_coding_agent/snip.py:34` | Minimum reads of the same path before snip fires for that path |
| `ToolResultStore.process_results_batch()` | `src/simple_coding_agent/tool_result_store.py:184` | Enforces per-item 50k and total 200k caps; externalizes largest-first |
| `DEFAULT_TOTAL_BUDGET_CHARS = 200_000` | `src/simple_coding_agent/tool_result_store.py:40` | Total inline budget (aggressive preset uses 8 000 via `max_inline_chars`) |
| `StderrTracer.emit()` — `externalize` channel | `src/simple_coding_agent/trace.py:91` | Emits `[trace] [externalize] bytes=N tool_use_id=...` at externalization time |
| `AgentLoop._maybe_snip()` | `src/simple_coding_agent/loop.py:638` | Guards snip to at most once per user turn via `_snip_attempted_this_turn` |
