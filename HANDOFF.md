# HANDOFF — RUNTIME_ACTIVATION_PLAN complete

> Updated by: M5 session
> Date: 2026-05-21
> Read this file FIRST in the next session, then verify against git/pytest.
>
> **There is no M6.** M5 was the terminal milestone of the
> RUNTIME_ACTIVATION_PLAN initiative. If you are reading this from the
> autonomous loop, the loop should stop here. If you are starting a new
> initiative against simple_coding_agent, write a fresh plan first.

---

## 1. Objective State

> The next session MUST re-verify these numbers. Do not trust this list
> blindly — re-run the commands.

- Last commit: `a3f51b1` — `git -C python-replica show a3f51b1` to inspect
- pytest: 497 passing (was 475 after M4, delta +22)
- mypy:   clean (Success: no issues found in 20 source files)
- ruff:   clean (All checks passed!)
- Branch: main

## 2. What M5 Accomplished

- A2: `openai_cli.py` gains `--repl` (plus `--max-steps`,
  `--max-context-tokens`, `--reserved-output-tokens`, `--resume`) and a
  new `_run_openai_repl` that builds an `OpenAIProvider`-backed
  `AgentLoop` via `cli._build_repl_loop` (with `provider=` injection)
  and delegates to the shared `cli._drive_repl_session`. The slash
  command surface (`/help`, `/stats`, `/save`, `/load`, `/remember`,
  `/exit`) is identical between MockProvider and live-provider REPLs.
- B4: New `src/simple_coding_agent/auto_learn.py` exposes
  pure-function `detect_cue(text) -> str | None` matching `记住`,
  `以后`, `don't` (apostrophe variants), and `prefer` (morphological
  siblings) plus a `format_hint(cue)` renderer. The REPL turn loop
  scans each user input with `detect_cue` and prints `format_hint`
  on stdout BEFORE the loop runs, so the operator sees the save
  target without inspecting code. Matches the M5 exit-gate marker
  `"记住" cue triggers save prompt`.
- B2-enabling: New `/remember <type> <id> <body...>` slash command in
  the REPL wires through `ProjectMemory.save()`, surfacing the
  existing secret-rejection and path-traversal guards. The REPL now
  wires a `ProjectMemory` (env-overridable via
  `SIMPLE_AGENT_MEMORY_DIR`, default `<workspace>/.simple-agent/memory/`)
  into every AgentLoop it constructs, making `MemorySelector` reachable
  end-to-end. `cli._drive_repl_session` was extracted from `_run_repl`
  for reuse by `openai_cli`.
- Plan 3.5 scenario 3: `tests/test_end_to_end_long_session.py` gains a
  test that seeds a `ProjectMemory` `feedback` entry, drives one REPL
  turn through `main()`, and proves both (a) the snippet appears in the
  provider's recorded `system` prompt (= `built.system`) and (b)
  `AgentStep.memory_injected` carries the snippet on the first step
  (verified via a direct `loop.run()` follow-up on the same instance).
- Tests: 22 new cases — `tests/test_auto_learn.py` (6),
  `tests/test_repl_slash_remember.py` (8),
  `tests/test_openai_cli_repl.py` (7),
  `tests/test_end_to_end_long_session.py` (+1).

## 3. Decisions Made That Diverge From Plan ⚠️

> THE MOST IMPORTANT SECTION. Any place reality diverged from
> RUNTIME_ACTIVATION_PLAN.md — alternative library, skipped test,
> renamed function, added abstraction, deferred work, etc. Include
> the WHY so any future session can decide whether to inherit or revert.

- **`cli._drive_repl_session` was extracted from `cli._run_repl` so
  `openai_cli._run_openai_repl` can reuse the read/run/exit machinery
  without duplication.** The plan implies A2 would ship as an
  independent REPL in `openai_cli.py`; in practice an exact duplicate
  of the slash command surface (≈150 LoC including `_handle_slash_command`,
  `_apply_resume`, `_handle_save_command`, `_handle_load_command`,
  the new `_handle_remember_command`, the KeyboardInterrupt + EOF
  handlers, and SessionMemory auto-save) would diverge over time. The
  extracted helper takes a pre-built `AgentLoop` and is what both REPL
  modes call.
- **`cli._build_repl_loop` was generalized with optional `provider=`
  and `system_prompt=` parameters** so `openai_cli` can inject its
  real-provider instance and coder-style system prompt without
  duplicating the AgentLoop wiring. When the parameters are omitted
  the existing MockProvider path is preserved exactly (every existing
  REPL test still passes unchanged).
- **`ProjectMemory` is auto-attached to every REPL `AgentLoop`** so
  the Jaccard selector and `_collect_memory_snippets` are reachable
  without explicit user wiring. The plan called for memory injection
  to be observable; it is hard to observe if the loop is constructed
  without a ProjectMemory. Storage dir resolution honours
  `SIMPLE_AGENT_MEMORY_DIR` (matching `memory_cli`); the workspace-
  relative fallback is `<workspace>/.simple-agent/memory/` (note:
  workspace-anchored, not cwd-anchored as in `memory_cli`) so REPL
  tests using `tmp_path` workspaces stay isolated.
- **`/remember` is implemented even though it was technically a B2
  task not explicitly listed in any milestone.** B4's exit gate is
  "cue triggers save prompt", and the prompt would be useless if there
  were no command to follow up with. `/remember` is the natural
  follow-up the prompt points at; it reuses every existing guardrail
  on `ProjectMemory.save()` (secret rejection, path traversal). This
  is documented in `cli._REPL_HELP_TEXT`.
- **The auto-learn hint is printed BEFORE the turn runs, not after.**
  The plan does not specify timing; printing before lets the operator
  read the hint while the provider call is in flight (and, in the
  MockProvider build, it is the only visible side-effect since the
  Mock answers are stock). Tests assert the hint string appears on
  stdout, not its position relative to the answer.
- **`tempfile` import was dropped from `openai_cli.py`** because the
  REPL mode receives an explicit `--workspace` (resolved by the
  existing `_resolve_workspace`) and there is no need to create a
  fresh tempdir; the one-shot mode already required `--workspace`.
- **The plan's `tests/test_repl_slash_commands.py` (5 cases for B2)
  ships as `tests/test_repl_slash_remember.py` (8 cases)** because
  the suite combines B2's `/remember` validation with B4's cue
  printing in the same REPL flow — the two are functionally one
  feature. File renamed to make the focus explicit.

## 4. Open Questions / Blockers for Next Initiative

> Anything needing human input, or pre-conditions for whatever comes
> next. If none, write "(none)".

- (none) — the RUNTIME_ACTIVATION_PLAN initiative is complete. Every
  P1–P8 mechanism that was unit-tested-only after the pre-M1 baseline
  is now reachable, observable, and demonstrable via the CLI: snip,
  full-compact, microcompact, reactive-compact, externalization,
  memory injection, session save/load/resume, and metrics counters.
  The next initiative against this repo can start from a clean
  follow-up plan document — there are no unresolved dependencies
  blocking it.

## 5. Next Session Prompt

> The initiative is complete; there is no next milestone to run.
> If the autonomous loop fires another session anyway, it should
> read this HANDOFF, observe that `git log -1 | grep "P9-M5"` matches,
> and stop. If a human session starts work on something new, paste
> a fresh plan instead of using a stale milestone prompt.

```
The RUNTIME_ACTIVATION_PLAN initiative is complete.

Last commit: a3f51b1 (P9-M5).
pytest: 497 passing.
mypy + ruff: clean.

If you are continuing to evolve simple_coding_agent, start by writing
a new plan document (do NOT reuse RUNTIME_ACTIVATION_PLAN.md -- that
plan's milestone table is exhausted). Read CLAUDE.md for the current
architecture and the completed P1-P9 roadmap, then propose the next
initiative with explicit milestones, exit gates, and a fresh HANDOFF
template before writing any code.
```
