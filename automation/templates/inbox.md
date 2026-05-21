# INBOX — write your next initiative brief here

> **You** edit this file. **Phase 1** (per `automation/RUNBOOK.md`) reads
> it, validates the YAML front-matter, and `git mv`s it into
> `initiatives/current/PLAN.md`. After that, this file is reset to the
> blank template so it's ready for the next initiative.
>
> Delete the entire `> placeholder` block below before saying "Run
> RUNBOOK Phase 1." — its presence signals the file has not been filled
> in and Phase 1 will refuse to proceed.

> placeholder: this INBOX has not been filled in yet. Replace the YAML
> below with real values and the markdown body with your actual brief.

---
slug: example-slug                # required, kebab-case [a-z0-9-]+
commit_prefix: example-prefix     # required, used in commit subjects: [<prefix>/M2] ...

milestones:                       # required, at least one entry
  M1:                             # key must match ^M[0-9]+$
    name: short-title-of-m1       # required
    phase_ids: [A1]               # required, free-form labels you can reference in PLAN
    exit_gate: |                  # required, concrete check the milestone agent will verify
      tests/test_x.py passing AND `simple-agent foo` prints "Y"
    notes: |                      # optional, anything Phase 1 should weave into the M1 prompt
      Implementation hint: ...
      Refer to claude-code-source-code/src/... for the analogous TS path.

  M2:
    name: short-title-of-m2
    phase_ids: [B1, B2]
    exit_gate: |
      `simple-agent --foo` returns exit code 0 AND README example matches.
    notes: |
      ...
---

# Goal

(One paragraph. What does this initiative add and why.)

# Background / motivation

(Optional.)

# Design sketch

(Optional. Key architectural choices, named classes/modules to add or
modify, data flow.)

# Risks / known unknowns

(Optional.)

# Out of scope (this initiative)

(Optional. List things adjacent observers might expect to see but you've
explicitly decided to defer.)

# Anything else

(Optional. Free-form. Phase 1 preserves everything below the YAML verbatim
into PLAN.md.)
