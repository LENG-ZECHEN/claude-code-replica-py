# docs/ — long-form documentation

This directory holds documentation that lives longer than any single
initiative. Architecture write-ups, ADRs, and one-off audits go here.

## Conventions

- One file per topic (don't mash architecture + ADRs into a single doc).
- Stable: a file here should outlive the milestone that produced it.
  Volatile state lives in [`../NOW.md`](../NOW.md) instead.
- Cross-link freely to source: use `[../src/foo.py:42](../src/foo.py)`.

## Sub-directories

- [`reports/`](./reports/) — one-off audits, retrospectives, and ad-hoc
  reviews that are not part of any initiative.

## Suggested files (not yet written)

- `ARCHITECTURE.md` — pipeline diagram and component boundaries (a
  graphical complement to the per-file summaries in `../CLAUDE.md`).
- `DECISIONS/` — Architecture Decision Records, one file per decision.
