# Initiatives — index

Each substantive piece of work that spans multiple milestones lives here
as a self-contained folder. The currently active one (if any) is in
[`current/`](./current/); completed ones are moved to
[`_archive/`](./_archive/) and never edited again.

For the active-initiative pointer and the bootstrap procedure, see
[`../NOW.md`](../NOW.md) and [`../automation/RUNBOOK.md`](../automation/RUNBOOK.md).

## Active

| Slug | Status | Bootstrapped | Milestones | Baseline |
|---|---|---|---|---|
| [`plan-surface`](./current/) | M1 next | 2026-06-08 | M1 → M3 | `17e616d` (pytest 835) |

## Archived

| Slug | Status | Period | Milestones | Final commit |
|---|---|---|---|---|
| [2026-05-runtime-activation](./_archive/2026-05-runtime-activation/) | complete | 2026-05-21 | M1 → M5 | `de3ecad` |
| [2026-05-observable-thresholds](./_archive/2026-05-observable-thresholds/) | complete | 2026-05-22 – 2026-05-23 | M1 → M3 | `026db2e` |
| [2026-05-obs-thr-harden](./_archive/2026-05-obs-thr-harden/) | complete | 2026-05-23 | M1 → M3 | `4582997` |
| [2026-05-ctx-mgmt-pdf-align](./_archive/2026-05-ctx-mgmt-pdf-align/) | complete | 2026-05-23 | M1 → M4 | `02f17f6` |
| [2026-05-auto-memory-overhaul](./_archive/2026-05-auto-memory-overhaul/) | complete | 2026-05-24 | M1 → M7 | `e9aef6a` |
| [2026-05-ctx-mgmt-demo](./_archive/2026-05-ctx-mgmt-demo/) | complete | 2026-05-25 | M1 → M3 | `f937d8f` |

## Folder shape (per initiative)

```
initiatives/<active-or-archived-slug>/
├── PLAN.md          # the brief (YAML front-matter + free-form markdown)
├── config.yaml      # machine-readable milestone table
├── HANDOFF.md       # cross-milestone state hand-off (rewritten each milestone)
├── PROGRESS.md      # append-only per-milestone log
├── prompts/         # detailed per-milestone prompt for the autonomous agent
│   ├── M1.md
│   └── ...
├── logs/            # raw claude --print logs from each milestone run
└── REVIEW.md        # post-execution audit (written by Phase 2 wrap-up)
```

> **Note on pre-RUNBOOK archives.** The
> [`2026-05-runtime-activation`](./_archive/2026-05-runtime-activation/)
> archive predates the current RUNBOOK and was backfilled by hand, so
> it lacks `config.yaml` and `REVIEW.md`, and its `logs/M*.log` files
> are short stubs rather than full `claude --print` session captures.
> All future initiatives go through Phase 1 / Phase 2 in
> [`../automation/RUNBOOK.md`](../automation/RUNBOOK.md) and produce
> the full shape above.
