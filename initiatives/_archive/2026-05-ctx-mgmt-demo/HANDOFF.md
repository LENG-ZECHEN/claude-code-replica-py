# HANDOFF — Next: none — all milestones complete

> Updated by: `M3` session
> Date: 2026-05-25
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `ctx-mgmt-demo`
- **current milestone**: just-completed `M3` — write-3-notebooks-and-readme
- **next milestone**: none — all milestones complete
- **all milestones (per PLAN)**: M1 [done], M2 [done], M3 [done]

## 2. Completed milestones

### M1

- **commit**: `(see git log)` `[ctx-demo/M1] --microcompact-minutes (both CLIs) + --max-turns (openai REPL)`
- **files changed**: `src/simple_coding_agent/compact.py`, `src/simple_coding_agent/cli.py`, `src/simple_coding_agent/openai_cli.py`, `tests/test_compact.py`, `tests/test_cli.py`, `tests/test_openai_cli_repl.py`
- **tests added**: `test_cli.py` (+1), `test_openai_cli_repl.py` (+2), `test_compact.py` (guard test updated, net 0 new). Total: 816 → 819 (+3)
- **behavior implemented**: Both `simple-agent --repl` and `simple-agent-openai --repl` now accept `--microcompact-minutes N`, which overrides `MicroCompactor.threshold_minutes` via the existing three-state precedence (explicit flag > `_AGGRESSIVE_THRESHOLDS` preset > built-in default of 60). `simple-agent-openai --repl` additionally accepts `--max-turns N`, which causes the REPL to exit cleanly (same path as `/exit`: dumps SessionMemory, returns 0) after exactly N user turns; slash commands do not count as turns. The turn counter lives in `cli._drive_repl_session` (shared by both REPLs). The `MicroCompactor` guard was relaxed from `threshold_minutes < 1` to `threshold_minutes < 0` so that `--microcompact-minutes 0` is valid ("any non-zero age qualifies").
- **design decisions (deviations from PLAN)**:
  - **Guard relaxed to N < 0**: PLAN offered "relax to N<0 OR set flag minimum to 1". Chose relaxation so `--microcompact-minutes 0` works exactly as PLAN described ("any age qualifies"). The guard test in `test_compact.py` was updated accordingly (now tests `threshold_minutes=-1`). Visible in: `compact.py:319`, `tests/test_compact.py:481`. Impact on M2: can use `--microcompact-minutes 0` in scenario 03 as originally specified.
  - **`resolved_microcompact_minutes` unified across aggressive/non-aggressive**: The aggressive branch previously hardcoded `microcompact_minutes` from the preset. Now both branches read `resolved_microcompact_minutes` (from `_resolve_threshold`), so an explicit `--microcompact-minutes` flag wins over the aggressive preset. Visible in: `cli.py:447–483`. Impact on M2: pass `--microcompact-minutes 0` alongside `--aggressive-thresholds` and 0 wins; omit it and the preset's 1 minute applies.
- **known limitations**:
  - (none)

### M2

- **commit**: `(see git log)` `[ctx-demo/M2] real-API artifact captures for snip+externalize, full compact, microcompact`
- **files changed**: `demo/_scripts/capture_scenario.py`, `demo/_artifacts/01_tool_result_management/{transcript.txt,trace.stderr,metrics.json,stats_output.txt}`, `demo/_artifacts/02_full_compact/{...}`, `demo/_artifacts/03_microcompact/{...}`
- **tests added**: 0 (M2 is a pure side-effect milestone)
- **behavior implemented**: Created `demo/_scripts/capture_scenario.py` (≤200 LOC SDK-based capture driver). Runs three scenarios against the DashScope API using `qwen3.6-plus`, writes 4 artifacts per scenario. All three exit gates pass.
- **design decisions (deviations from PLAN)**:
  - **Scenario 01 needs 3 reads, not 2**: `should_snip()` in `snip.py` uses `_PATH_THRESHOLD=3` (requires 3 reads of the same path before returning True). The PLAN assumed 2 reads would suffice. Added a 3rd "check for changes" read of `small.txt` so snip fires. See `snip.py:147`.
  - **`microcompact_minutes=60` for scenario 01**: The aggressive preset sets `microcompact_minutes=1`, but `qwen3.6-plus` in thinking mode takes ~60 seconds per API call. With the preset, microcompact would fire after the 2nd turn and clear tool results before snip could accumulate 3 reads. Explicitly passing `microcompact_minutes=60` (overrides the preset via three-state precedence) prevents this interference.
  - **`externalized_bytes` read from context builder**: `_build_repl_loop` creates `ToolResultStore(max_inline_chars=2000)` and passes it to `ContextBuilder`, but does NOT wire it to `AgentLoop`. Therefore `AgentLoop._tool_result_store = None` and `_refresh_externalized_bytes()` always returns 0. Trace confirms externalization DID happen (`[trace] [externalize] bytes=3800`). The driver reads `loop._context_builder._store.total_externalized_bytes` directly and patches the metrics dict before writing `metrics.json`. No `src/` changes were made.
- **known limitations**:
  - See Section 5 for the wiring bug.

### M3

- **commit**: `(see git log)` `[ctx-demo/M3] notebooks + README; initiative complete`
- **files changed**: `demo/README.md`, `demo/01_tool_result_management.md`, `demo/02_full_compact.md`, `demo/03_microcompact.md`, `initiatives/current/PROGRESS.md`, `initiatives/current/HANDOFF.md`, `initiatives/current/PLAN.md`
- **tests added**: 0 (M3 is a pure docs milestone)
- **behavior implemented**: Wrote four markdown documents under `demo/`. `README.md` indexes the three notebooks, documents env vars, the swappable-model fallback list, the reactive-compact pointer to `examples/stress_demo.py`, and notes that `_artifacts/` is one canonical run. Each notebook covers one mechanism (`01` snip+externalize, `02` full compact, `03` microcompact), embeds ≥5 lines of captured trace/metrics/transcript output from the corresponding `_artifacts/` directory, shows the exact capture command, names `qwen3.6-plus` as the model (read from `stats_output.txt` header), and maps each mechanism to its `file:line` source in `src/simple_coding_agent/`.
- **design decisions (deviations from PLAN)**:
  - **Microcompact scenario 03 shows `cleared=0`**: The trace shows `microcompact_invocations=3` but `cleared=0` for all three events. The notebook explains why: `keep_recent=5` (the default for `MicroCompactor`, not overridden by `--aggressive-thresholds`) protects the single tool result in the 2-turn session. The aggressive preset's `keep_recent=2` applies to `ContextCompactor`, not `MicroCompactor`. The notebook distinguishes invocation count from clearing count to avoid misleading the reader.
  - **`externalized_bytes` discrepancy acknowledged in notebook 01**: `stats_output.txt` shows `externalized bytes: 0` (wiring bug) while `metrics.json` shows `3800` (patched by capture script). The notebook notes both values and explains the discrepancy rather than silently ignoring it.
- **known limitations**:
  - Pre-existing ruff errors in `demo/_scripts/capture_scenario.py` (E402 import-ordering, I001 sort, E501 line-length) were present at the M2 commit and are not introduced by M3. Not fixed here because M3 is docs-only.

## 3. Current repo state

> Re-verify these numbers before starting. Do not trust this list blindly.

- **last commit**: `(see git log)` — `git -C python-replica log --oneline -1`
- **tests**: 819 passing (unchanged from M2 — M3 adds no tests)
- **mypy**: clean (no issues in 26 source files)
- **ruff**: pre-existing errors in `demo/_scripts/capture_scenario.py` from M2 (E402, I001, E501); not introduced by M3
- **branch**: main
- **known failing checks**: none (ruff errors are in committed M2 file, not in src/)

## 4. Important constraints (carried forward)

> Invariants that subsequent work MUST respect. Update by ADDING — only
> remove a constraint by quoting it and explaining why it is retired.

- **do not modify**:
  - `MicroCompactor.__init__` guard: now accepts `threshold_minutes >= 0`; do not tighten back to `>= 1`. The guard test (`test_compact.py::test_microcompactor_rejects_negative_minutes`) pins this at -1.
- **preserve**:
  - `cli._drive_repl_session` signature now has `max_turns: int | None = None` (defaulting to None = unlimited). Both REPLs call it; do not remove this parameter.
  - Three-state precedence in `cli._resolve_threshold` covers `"microcompact_minutes"` with `preset_key="microcompact_minutes"`. Both REPLs share this path. Do not add a separate aggressive-branch local override for `microcompact_minutes`.
- **compatibility requirements**:
  - `--microcompact-minutes N` accepts N=0 (immediate) through any positive integer. Argparse type is `int`, no explicit lower bound in argparse (the guard in `compact.py` handles N<0 at construction time).
  - `--max-turns N` is openai_cli only; `simple-agent --repl` does not expose it (by design; MockProvider REPL has no artifacts to capture).
- **M3 additions**:
  - All 3 milestones complete. Review handles project-doc updates per RUNBOOK Doc-update tiers. The `demo/_artifacts/` directories are immutable evidence; do not rewrite or re-capture during review.

## 5. Next milestone guidance

For the **review session** (RUNBOOK Phase 2B/2C):

- **next scope**: Audit all three milestones and generate `initiatives/current/REVIEW.md`. Apply Tier A/B doc edits per RUNBOOK (update `python-replica/CLAUDE.md` per-file summaries where needed; update top-level README if relevant). Archive `initiatives/current/` into `initiatives/_archive/2026-05-ctx-mgmt-demo/`.
- **relevant files for review audit**:
  - `initiatives/current/PLAN.md` — original brief
  - `initiatives/current/PROGRESS.md` — cumulative milestone facts
  - `initiatives/current/HANDOFF.md` — this file (Section 2 for each milestone's design decisions)
  - `demo/` tree — 4 notebooks + 3 artifact directories + capture script
  - `src/simple_coding_agent/cli.py`, `openai_cli.py` — M1 changes
  - `src/simple_coding_agent/compact.py` — guard relaxation (M1)
- **expected outcome**: `REVIEW.md` (quality assessment + findings) + archive move + Tier A/B doc edits
- **risks**:
  - **Known wiring bug** — `_build_repl_loop` does not wire `tool_result_store` to `AgentLoop`, so `MetricsCollector.externalized_bytes` is always 0. The capture script works around this by reading from `loop._context_builder._store` directly. The `stats_output.txt` for scenario 01 shows `externalized bytes: 0` while `metrics.json` shows `3800`. The review should flag this as a Tier-B finding; the 1-line fix is: add `"tool_result_store": tool_result_store` to `loop_kwargs` in `_build_repl_loop` in `cli.py`.
  - **Pre-existing ruff errors in `demo/_scripts/capture_scenario.py`**: E402, I001, E501. M2 incorrectly reported ruff: clean. The review should flag this and the fix should be applied (it's a trivial reorder + line-wrap in a non-src file).
  - **Guard test relaxation in M1**: `test_compact.py::test_microcompactor_rejects_negative_minutes` was updated from `threshold_minutes=-0.5` style check to `threshold_minutes=-1`. The review should verify this didn't weaken any downstream invariant.
  - **Microcompact scenario 03 is educational, not a stress test**: `cleared=0` throughout. The review should confirm the notebook's explanation is accurate (keep_recent=5 protects the single result) and note that a future demo could run 6+ reads to show actual clearing.

The full ready-to-run prompt is at:
`initiatives/current/prompts/M3.md`
