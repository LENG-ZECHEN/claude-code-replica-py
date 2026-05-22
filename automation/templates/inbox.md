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
  #
  # SIZING GUIDANCE — read before splitting your work.
  # Each milestone runs in ONE `claude --print` session. Claude Code's
  # auto-compact thrash-loop protection (v2.1.89+) silently terminates a
  # session that re-fills its context 3x post-compact (exit 0, no commit,
  # 1-byte log). M1 of observable-thresholds hit this at turn 243.
  #
  # Split a milestone into M{N}a / M{N}b / M{N}c when ANY of these is true:
  #   - touches > 6 source files in src/
  #   - introduces a Protocol / required constructor param / pure-function
  #     signature change that propagates to > 4 components
  #   - adds > 15 new test cases
  #   - combines "introduce abstraction" + "wire it everywhere" +
  #     "expose via CLI" in a single milestone (the M1 pattern)
  #
  # Suggested split shape for cross-cutting work:
  #   M{N}a = introduce the abstraction + focused unit tests
  #   M{N}b = wire it into existing components (the migration)
  #   M{N}c = expose via CLI flag + integration tests
  #
  # Phase 1 will re-assess sizing per RUNBOOK §"Milestone sizing assessment"
  # before generating prompts. If you're confident the work is atomic and
  # must stay in one milestone, write a `> SIZING WAIVED: <rationale>` note
  # under "Anything else" so Phase 1 can record it in PLAN.md provenance.
  #
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

(Optional. What changed in the project or world that makes this the right
time. Tickets, conversations, prior incidents that triggered this work.)

# Design sketch

(Optional. Key architectural choices, named classes/modules to add or
modify, data flow. NOT a complete spec — milestone prompts will fill in
detail.)

# Risks / known unknowns

(Optional. What might break, what the agent might trip over, what to
verify manually before declaring done.)

# Out of scope (this initiative)

(Optional. List things adjacent observers might expect to see but you've
explicitly decided to defer. Helps the milestone agent not to drift.)

# Anything else

(Optional. Free-form. Phase 1 preserves everything below the YAML verbatim
into PLAN.md, so you can add any sections you like.)
