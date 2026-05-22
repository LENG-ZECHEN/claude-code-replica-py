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
- `DECISIONS/` — Architecture Decision Records, one file per decision.
  Auto-created by review sessions (see below) the first time an ADR is
  needed; thereafter you can also write ADRs by hand.

## Auto-population by review sessions

Some files in this directory may be **created or appended** automatically
by the Phase 2 review session of an initiative (see
[`../automation/RUNBOOK.md`](../automation/RUNBOOK.md) section "Doc-update
tiers"). The bias is **moderately aggressive**: when triggers match,
the review session prefers to write over propose.

What the review session may do automatically:

- **Create** `docs/<slug>.md` (subsystem doc) when the initiative adds
  a new `src/` subdirectory or a substantial new module. The template
  is [`../automation/templates/subsystem_doc.md`](../automation/templates/subsystem_doc.md).
- **Create** `docs/DECISIONS/<NNNN>-<slug>.md` (ADR) when the initiative's
  `HANDOFF.md` Section 2 (per-milestone "design decisions") records
  architectural divergences. The template is
  [`../automation/templates/adr.md`](../automation/templates/adr.md).
- **Append** a `## Recent changes` bullet to an existing `docs/<slug>.md`
  when a later initiative touches the same subsystem.

What the review session will NEVER do automatically:

- Overwrite an existing file's body (only append to a `## Recent changes`
  section).
- Delete any file in `docs/`.
- Rewrite an existing ADR (only mark it `superseded by` and create a new
  one).
- Edit `reports/` files (those are frozen artifacts).

Anything outside the above — rewrites, reorganizations, structural
changes — is **proposed** in the initiative's `REVIEW.md` and waits for
you to apply manually.

## Suggested files (not yet written)

- `ARCHITECTURE.md` — pipeline diagram and component boundaries (a
  graphical complement to the per-file summaries in `../CLAUDE.md`).
  Write this by hand; review sessions do not auto-generate it because
  diagrams + cross-cutting prose are hard to keep coherent across
  sessions.
