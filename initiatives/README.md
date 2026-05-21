# Initiatives — index

Each substantive piece of work that spans multiple milestones lives here
as a self-contained folder. The currently active one (if any) is in
[`current/`](./current/); completed ones are moved to
[`_archive/`](./_archive/) and never edited again.

For the active-initiative pointer and the bootstrap procedure, see
[`../NOW.md`](../NOW.md) and [`../automation/RUNBOOK.md`](../automation/RUNBOOK.md).

## Active

| Slug | Status | Started | Goal |
|---|---|---|---|
| _(none)_ | — | — | `initiatives/current/` is empty |

## Archived

| Slug | Status | Period | Milestones | Final commit |
|---|---|---|---|---|
| [2026-05-runtime-activation](./_archive/2026-05-runtime-activation/) | complete | 2026-05-21 | M1 → M5 | `de3ecad` |

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
