# Notebook 03 — Microcompact

This notebook demonstrates **MicroCompactor**: the cold-cache cleanup mechanism that clears
`ToolResult` content for compactable tools (`read_file`, `run_shell`, `search_text`,
`list_files`) when the most recent assistant message is old enough. Microcompact targets
the case where a long pause (or a very slow model response) makes previously-read file content
stale — the model no longer needs it, but it still occupies context tokens.

This session uses `--microcompact-minutes 0`, which fires microcompact after any non-zero
elapsed time since the last assistant message. The artifacts show that microcompact fires three
times, but the single tool result in this short session is protected by `keep_recent=5` and
is never cleared.

---

## Setup

**Environment**: `python-replica/.env` — sets `DASHSCOPE_API_KEY`, `OPENAI_BASE_URL`, and
`SIMPLE_AGENT_MODEL`.

**Capture command** (run from `python-replica/`):

```console
python demo/_scripts/capture_scenario.py 03
```

The script uses `_build_repl_loop` with `aggressive_thresholds=True` and
`microcompact_minutes=0`. Key thresholds:

| Setting | Value | Source |
|---------|-------|--------|
| `microcompact_minutes` | 0 (explicit flag overrides aggressive preset's 1 min) | `cli._resolve_threshold` three-state precedence |
| `keep_recent` (MicroCompactor) | 5 (default — **not** affected by `--aggressive-thresholds`) | `_DEFAULT_MICROCOMPACT_KEEP_RECENT` at `cli.py:102` |
| `context_tokens` | 4 000 | aggressive preset |

**Model** (from `_artifacts/03_microcompact/stats_output.txt`):

```text
# model: qwen3.6-plus
```

**Workspace file**: `notes.txt` (65 chars).

**Scenario script** (2 user turns):

1. "Please use the read_file tool to read notes.txt and tell me its contents."
2. "What do you remember from the notes.txt file you just read?"

---

## Step-by-step

### 1. First provider call — microcompact fires with no results to clear

When turn 1 begins, the transcript has only the first user message. `_maybe_microcompact()`
calls `should_microcompact()`: because there are no assistant messages yet, the function returns
`True` by default (see `compact.py:355`). Microcompact runs, finds zero compactable tool results,
and emits:

```text
[trace] [microcompact] cleared=0 messages=1
```

The invocation counter increments even though nothing was cleared — `cleared=0` is the correct
outcome here, not a sign of failure.

### 2. After tool execution — microcompact fires again

The model calls `read_file(notes.txt)`, the tool result is appended to the transcript, and the
loop re-enters the top of its inner while-loop for the text response. At this point the
transcript has 3 messages: `[user1, assistant(tool_use), user(tool_result)]`.

`_maybe_microcompact()` checks whether the current latest-assistant UUID matches the last
compacted one. It doesn't (new tool_use was just appended), so it proceeds. With
`threshold_minutes=0`, `should_microcompact()` returns `True` as long as any elapsed time has
passed since the tool_use was created — satisfied after a real API call.

Microcompact runs over the 3-message transcript:

```text
[trace] [microcompact] cleared=0 messages=3
```

The tool result for `notes.txt` is a compactable result, but `_recent_compactable_positions()`
preserves the `keep_recent=5` most recent compactable results. Since there is only one result,
it is in the protected window and is **not** cleared. `cleared=0` is correct.

From `_artifacts/03_microcompact/transcript.txt`:

```console
## 1. user (text)
Please use the read_file tool to read notes.txt and tell me its contents.

## 3. user (tool_result)
tool_result: Microcompact demo: data cleared when threshold_minutes=0 fires next turn.

## 4. assistant (text)
The contents of notes.txt are:
"Microcompact demo: data cleared when threshold_minutes=0 fires next turn."
```

The tool result content is intact (not `[CLEARED]`) because `keep_recent=5` protects it.

### 3. Turn 2 — microcompact fires a third time

After the user asks "What do you remember?", the transcript has 5 messages. The loop runs
`_maybe_microcompact()` again (the latest-assistant UUID changed when the text response in
turn 1 was appended). The time threshold is satisfied. Microcompact runs:

```text
[trace] [microcompact] cleared=0 messages=5
```

Still `cleared=0`: the `read_file` result is the only compactable result, and it is still in
the `keep_recent=5` window. The model answers from its in-context copy of the notes.

```console
## 6. assistant (text)
The content of `notes.txt` was:
"Microcompact demo: data cleared when threshold_minutes=0 fires next turn."
```

### 4. Final metrics

From `_artifacts/03_microcompact/metrics.json`:

```json
{
  "full_compacts": 0,
  "snip_invocations": 0,
  "microcompact_invocations": 3,
  "reactive_compacts": 0,
  "externalized_bytes": 0,
  "tokens_per_turn": [58, 161, 220]
}
```

From `_artifacts/03_microcompact/stats_output.txt`:

```text
# model: qwen3.6-plus
Context-management metrics:
  full compacts:         0
  reactive compacts:     0
  microcompact runs:     3
  snip runs:             0
  externalized bytes:    0
  turns recorded:        3
```

Three invocations, zero clears. This is the expected behaviour for a 2-turn session with a
`keep_recent=5` window: the time threshold fires on every inner-loop iteration, but the
protected window ensures the single recent tool result is never discarded.

---

## What to look for

| Signal | Where | What it proves |
|--------|-------|---------------|
| `[trace] [microcompact] cleared=0 messages=1` | `trace.stderr` line 1 | Fires before first API call; no results to clear yet |
| `[trace] [microcompact] cleared=0 messages=3` | `trace.stderr` line 4 | Fires after tool_use appended; result exists but protected by keep_recent |
| `[trace] [microcompact] cleared=0 messages=5` | `trace.stderr` line 7 | Fires again at turn 2; keep_recent still protects the single result |
| `"microcompact_invocations": 3` | `metrics.json` | Invocation counter tracks threshold-satisfied events, not clearing events |
| Tool result intact in transcript | `transcript.txt` message 3 | `cleared=0` means keep_recent is doing its job — result is preserved |

**Key insight**: `microcompact_invocations` counts how often `should_microcompact()` returns
`True`, not how often content is actually cleared. In a longer session where the same file has
been read many times and older reads exceed `keep_recent=5`, those older results would be cleared.
Here, with only one result and `keep_recent=5`, the counter shows activity but the context is
unchanged. To observe actual clearing, run more than 5 `read_file` calls in a session with a
high enough `threshold_minutes` to let them age.

**Why microcompact fires 3 times (not once)**: `AgentLoop._maybe_microcompact()` guards by
`_microcompacted_against_assistant_uuid`, not by a boolean flag. It skips if the latest assistant
UUID matches the last processed one. Each new provider call that produces a new assistant message
(tool_use or text) changes that UUID, allowing the next inner-loop iteration to run microcompact
again. In this session: first call (no prior assistant), tool_use call, and text response — three
distinct assistant UUIDs → three microcompact runs.

---

## Source mapping

| Mechanism | File:line | What it does |
|-----------|-----------|-------------|
| `MicroCompactor.should_microcompact()` | `src/simple_coding_agent/compact.py:327` | Returns True when no assistant messages exist, or when latest assistant message is older than `threshold_minutes` |
| `MicroCompactor.microcompact()` | `src/simple_coding_agent/compact.py:360` | Rewrites compactable tool results to `CLEARED_TOOL_RESULT_CONTENT`; preserves `keep_recent` most recent; emits trace |
| `AgentLoop._maybe_microcompact()` | `src/simple_coding_agent/loop.py:613` | Guards by `_microcompacted_against_assistant_uuid`; calls should_microcompact + microcompact; records metric |
| `--microcompact-minutes` (cli.py) | `src/simple_coding_agent/cli.py:987` | Argparse flag for `simple-agent`; plumbed through `_resolve_threshold` for three-state precedence |
| `--microcompact-minutes` (openai_cli.py) | `src/simple_coding_agent/openai_cli.py:143` | Same flag for `simple-agent-openai`; delegates to `_build_repl_loop(microcompact_minutes=...)` |
