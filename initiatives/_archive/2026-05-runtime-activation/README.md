# Runtime Activation Initiative (2026-05) — Archived

**Status:** complete
**Period:** 2026-05-21 (single day, autonomous loop)
**Milestones:** M1 → M5
**Final commit:** `de3ecad`
**pytest delta:** 392 → 497 (+105)

## What this initiative did

Before this initiative, every context-management mechanism (snip, full-compact,
microcompact, reactive-compact, externalization) and every memory mechanism
(SessionMemory / ProjectMemory persistence, memory injection, auto-learn cues)
was implemented and unit-tested but unreachable from the CLI. A one-shot run
of `simple-agent` never lived long enough to trigger any of them.

Five milestones added the runtime entry points so each mechanism becomes
reachable, observable, and demonstrable from the CLI:

| Milestone | Final commit | Adds |
|---|---|---|
| M1 | `4cdbc79` | `--repl`, `--max-steps`, `--max-context-tokens`, `--reserved-output-tokens`, `--stream`, `simple-agent memory ...` CLI |
| M2 | `55dc845` | `examples/stress_demo.py`, `examples/microcompact_demo.py` (deterministic compaction triggers) |
| M3 | `7a3bb51` | `MetricsCollector`, REPL `/stats`, `SessionMemory.dump_json/load_json` auto-persist |
| M4 | `ea7e383`, `2aa9706` | `Transcript.dump_json/load_json`, `session_store.py`, REPL `/save` `/load`, top-level `--resume` |
| M5 | `a3f51b1`, `de3ecad` | `openai_cli --repl`, `auto_learn.py` cues, REPL `/remember`, end-to-end memory-injection scenario |

## Files in this archive

- `PLAN.md` — the original `RUNTIME_ACTIVATION_PLAN.md` (sections 1–6,
  sealed with a STATUS header)
- `HANDOFF.md` — terminal-milestone handoff (M5 → none)
- `PROGRESS.md` — append-only per-milestone log (M1–M5)
- `logs/` — raw `claude --print` logs from each milestone run plus
  the wrapping loop log

## Why this is preserved

Future initiatives bootstrap from `automation/INBOX.md` into
`initiatives/current/`. After completion they move here. The artifacts
in this folder remain searchable evidence of what was attempted, what
diverged from plan, and what the final shape was. Subsequent initiatives
can read this folder's `HANDOFF.md` Section 3 ("Decisions That Diverge")
for inherited assumptions.
