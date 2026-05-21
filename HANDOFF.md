# HANDOFF — Next: M5

> Updated by: M4 session
> Date: 2026-05-21
> Read this file FIRST in the next session, then verify against git/pytest.

---

## 1. Objective State

> The next session MUST re-verify these numbers. Do not trust this list
> blindly — re-run the commands.

- Last commit: `ea7e383` — `git -C python-replica show ea7e383` to inspect
- pytest: 475 passing (was 455 after M3, delta +20)
- mypy:   clean (Success: no issues found in 19 source files)
- ruff:   clean (All checks passed!)
- Branch: main

## 2. What M4 Accomplished

- D1: `Transcript` gains `to_jsonable` / `from_jsonable` / `dump_json` /
  `load_json` in `src/simple_coding_agent/transcript.py`. `dump_json`
  drops `is_virtual` messages by default; `from_jsonable` validates the
  five required per-message fields (`uuid`/`role`/`content`/`timestamp`/
  `type`) and unknown enum values, raising `ValueError` with the field
  name in the message so callers can `pytest.raises(ValueError,
  match="uuid")`. A new free `_atomic_write_json` helper centralises
  the `tempfile.mkstemp` + `os.replace` pattern shared with
  `SessionMemory.dump_json`. Six tests in
  `tests/test_transcript_persist.py`.
- D2: New `src/simple_coding_agent/session_store.py` exposes
  `save_session` / `load_session` / `session_path_for` /
  `resolve_sessions_dir`, typed errors `InvalidSessionNameError` +
  `SessionNotFoundError`, and a `_SAFE_SESSION_NAME_PATTERN`
  matching `ProjectMemory`'s regex. `cli.py` adds `/save <name>` and
  `/load <name>` slash commands (with `/help` entries) that mutate the
  active `AgentLoop` in place via `_transcript.replace_all()` and
  `_last_summary = ...`. `SIMPLE_AGENT_SESSIONS_DIR` env var redirects
  the default `~/.simple-agent/sessions/` for test isolation. Eight
  tests in `tests/test_repl_save_load.py`.
- D3: `cli.py` gains a top-level `--resume <name>` flag (implicit
  `--repl` when only `--resume` is given), driven by a new
  `_apply_resume(name, loop)` helper that returns exit code 2 on a
  clear failure (invalid name, missing file, schema error) and 0 on
  success. Four tests in `tests/test_resume_session.py` plus two
  integration scenarios in `tests/test_end_to_end_long_session.py`
  (plan 3.5 scenarios 1 + 2). The kill-then-resume exit gate is
  exercised end-to-end via two `main()` invocations per integration
  test, with separate workspace tempdirs guaranteeing no in-process
  carryover.

## 3. Decisions Made That Diverge From Plan ⚠️

> THE MOST IMPORTANT SECTION. Any place reality diverged from
> RUNTIME_ACTIVATION_PLAN.md — alternative library, skipped test,
> renamed function, added abstraction, deferred work, etc. Include
> the WHY so the next session can decide whether to inherit or revert.
>
> If nothing diverged, write "(none)" — do NOT delete the section.

- **`Transcript` exposes a `to_jsonable` / `from_jsonable` layer above
  the raw `dump_json` / `load_json` filesystem methods, rather than
  the in-place persistence the plan implied.** The split was needed
  so `session_store.save_session` could compose a single JSON payload
  (`{transcript: {...}, last_summary: {...}}`) without writing the
  transcript and the summary to two separate files. The filesystem
  wrappers (`dump_json` / `load_json`) remain on Transcript as
  documented in plan section 2 D1; they delegate to
  `to_jsonable` / `from_jsonable` + a shared `_atomic_write_json`. No
  behaviour from the plan was dropped — only one extra public method
  pair was added.
- **`--resume <name>` returns exit code 2 (not 1) on a clear startup
  failure**, so harness scripts (and the shell loop's exit-gate
  greps) can distinguish a startup failure from a normal `/exit` (0)
  or a generic runtime issue. The plan did not specify a code; 2 is
  the conventional "misuse of arguments" code and matches what
  `argparse` already uses for unknown flags.
- **`--resume <name>` without `--repl` implicitly enables REPL
  mode.** The plan listed both `simple-agent --resume <name>` and
  `--repl --resume <name>` as valid surfaces. Rather than enforce a
  separate code path or error out when `--repl` is omitted, `main()`
  ORs the two booleans (`args.repl or args.resume is not None`) and
  dispatches to `_run_repl(... resume=args.resume)`. The one-shot
  demo path was preserved as the default when neither flag is given.
- **`_handle_slash_command` is now mutating** (it can rewrite
  `loop._transcript` and `loop._last_summary` via `/load`), where
  previously it only printed. The mutation is in-place because the
  REPL holds a single `AgentLoop` instance for the entire process —
  re-creating one would discard `metrics`, `session_memory`, and
  every other dependency wired at construction time. This is
  consistent with `Transcript.replace_all`, which exists for exactly
  this purpose.
- **`tests/test_end_to_end_long_session.py` ships with the 2
  scenarios from plan section 3.5 that are in M4 scope (scenarios 1
  and 2)**; scenario 3 (memory injection) is deliberately deferred
  to M5 per the plan's milestone table (M5 picks up scenario 3
  alongside Phase A2 + B4).
- **Manual smoke run of `simple-agent --repl --resume smoke` was
  attempted but the autonomous-loop sandbox blocked the required
  multi-operation shell command and the destructive cleanup.** The
  exit gate is still proven by the two integration tests in
  `tests/test_end_to_end_long_session.py`, each of which runs two
  separate `main()` invocations with different workspaces — the
  same shape as a kill-then-resume cycle. The leftover
  `/Users/leng/my-cc-py/.m4-smoke/` directory is empty (two empty
  subdirs created during the attempted smoke), outside the
  `python-replica/` git tree, and has no impact on the
  repository state.

## 4. Open Questions / Blockers for M5

> Anything needing human input, or pre-conditions for M5.
> If none, write "(none)".

- (none) — all M4 gates green. M5 picks up Phase A2 (openai_cli REPL),
  B4 (auto-learn cues from user input like "记住" / "以后" / "don't" /
  "prefer"), and the 3.5 scenario 3 (memory injection affects
  response). The `session_store` API is stable; M5 may reuse
  `resolve_sessions_dir()` if it adds new persistence surfaces, but
  no schema changes are anticipated.

## 5. Next Session Prompt

> Paste the content of the fenced block below into a fresh `claude`
> session opened from `python-replica/`. The prompt is self-contained;
> the next session needs nothing from the current conversation.

```
I'm continuing work on simple_coding_agent, a Python replica of Claude
Code v2.1.88's context-management and memory pipeline.

Before doing anything:
1. Read CLAUDE.md (architecture + completed P-roadmap).
2. Read RUNTIME_ACTIVATION_PLAN.md
     - Section 4 for milestone M5's scope
     - Section 5 for execution rules
3. Read HANDOFF.md — pay close attention to Section 3
   "Decisions Made That Diverge From Plan".
4. Run `git log --oneline -10` and `pytest --tb=no -q` to confirm
   the baseline matches HANDOFF.md Section 1.

Then execute Milestone M5 only:
  - A2 + B4    (from RUNTIME_ACTIVATION_PLAN.md Section 2)

Follow Section 5 "Execution Rules" in RUNTIME_ACTIVATION_PLAN.md
strictly. The exact test case lists are in plan Section 3.2
(`test_repl_slash_commands.py` for /remember + B4 auto-learn) plus
the cross-session integration scenario 3 in 3.5.

Out of scope: any other milestone. Do NOT touch out-of-milestone code.

Exit ritual for this session (MANDATORY — do all five before stopping):
  1. Milestone M5's exit gate (per plan Section 4) is met
     — openai_cli --repl works; "记住" cue triggers save prompt.
  2. `git commit -m "P9-M5: <one-line>"` has landed.
  3. CLAUDE.md updated with a P9-M5 entry mirroring P1-P8 format.
  4. PROGRESS.md appended with a one-line summary.
  5. HANDOFF.md overwritten using templates/handoff_template.md, with
     all placeholders filled, to hand off to the M6 session (or mark
     the initiative complete if M5 is the last milestone).

Confirm you've read all three files (CLAUDE.md, RUNTIME_ACTIVATION_PLAN.md,
HANDOFF.md), then ask me to approve before starting implementation.
```
