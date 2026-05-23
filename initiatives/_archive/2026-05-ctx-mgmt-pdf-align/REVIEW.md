# REVIEW — ctx-mgmt-pdf-align

## Summary

- Initiative period: 2026-05-23 -> 2026-05-23
- Milestones: 4 (M1–M4), all complete
- pytest: 615 -> 704 (delta +89)
- mypy: clean (22 source files)
- ruff: clean
- Total commits in this initiative: 5 (1 bootstrap + M1–M4) in `8f1d98f..HEAD`
- Final pre-wrap commit: `02f17f6` `[ctx-pdf/M4] model-driven-snip-tool`
- Review mode: multi-agent staged review (`code-reviewer` + `doc-curator-candidate-finder` in parallel, then reconciled by the main agent, then `demo-narrator`)

## Lessons learned

- **Per-milestone test-count chaining is fragile across session boundaries.** M4's HANDOFF/PROGRESS recorded a phantom baseline (685) that never existed in the commit chain (615→632→647→670→704). Future milestone prompts should require the exit ritual to quote `pytest --collect-only -q | tail -1` at *both* the start and end of the milestone, not a remembered number.
- **An all-MockProvider suite cannot catch API-payload shape bugs.** Both the prepended-attachment/nudge same-role risk (M3+M4) and the `<msg uuid="...">` wrap survival (M4) are invisible to 704 green tests. A live `OpenAIProvider` smoke run should be a named exit-gate item whenever a milestone changes the serialized payload shape.
- **The SIZING WAIVED note for M4 was accurate.** M4 touched exactly 6 src files (the predicted ceiling) and finished in one session despite a quota-truncated log; the upfront sizing call held. Keep documenting the split seam even when not used.
- **Strong, concrete prompts paid off.** All four prompts scored ≥39/40; the explicit expected-files lists, do-not enumerations, and AND-clause-by-AND-clause evidence requirements meant the milestone agents had little room to drift. This pattern is worth keeping as the template default.
- **Tier B ADR auto-creation worked cleanly** because HANDOFF Section 2 carried the divergence record in a parseable shape. The ADR (`0002`) was assembled directly from the M2/M3/M4 design-decision subsections.

## Main-agent reconciliation note

- **Conflict between subagents?** None. The `code-reviewer` (code quality + scorecards) and `doc-curator-candidate-finder` (doc tiers) addressed disjoint surfaces. They independently converged on the same fact — the M4 test-count discrepancy (code-reviewer as a HANDOFF-accuracy defect; doc-curator implicitly via the 615→704 chain) — with no contradiction.
- **Independent verification by the main agent:**
  - The phantom-685 finding was confirmed by adding a throwaway `git worktree` at `646bf2c` and running `pytest --collect-only -q`: **670 tests collected**, not 685. The true M4 delta is **670 → 704 (+34)**. Retained at MEDIUM (documentation-accuracy defect; the exit gate "≥15 growth from M3-post" is still objectively satisfied by +34).
  - The consecutive-same-role finding was confirmed by reading `context.py:278-281`: the nudge dict and `_attachment_dicts(...)` output (both user-role) are prepended **after** `_normalize_messages` (the only same-role merge site) and **after** the trim/orphan pass. Retained at MEDIUM, flagged as untested against a real endpoint.
- **Severity adjustments:** none. All code-reviewer severities accepted as submitted.
- **Scorecard corrections:** none. The `code-reviewer` scorecards are accepted verbatim as the source of truth.
- **Doc decisions:** Tier A CLAUDE.md summary — APPLIED. Tier B ADR-0002 — CREATED. Tier B standalone subsystem doc (`docs/snip-tool-model.md`) — SKIPPED (would duplicate the CLAUDE.md summary + ADR; doc-curator itself recommended folding it in). Two Tier C proposals — INCLUDED below for human review.
- **Owner-brief findings selected:** both MEDIUM findings (phantom-685; same-role payload risk) plus the LOW empty-`snip_history` finding, plus a note that docs were updated and which Tier C items remain. The M2 message-granularity LOW was kept in this REVIEW only (already a documented known limitation; not owner-actionable).

### Reconciled prompt quality scorecards

| Milestone | Clarity | Completeness | Scope alignment | Constraint specificity | Exit-ritual correctness | Out-of-scope enumeration | Mandatory reading completeness | Exit gate objectivity | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| M1 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 40/40 |
| M2 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 40/40 |
| M3 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 4 | 39/40 |
| M4 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 4 | 39/40 |

- **M3 — Exit gate objectivity (4):** the "NOT counted toward keep_recent budget trimming" clause is a negative/behavioral property no single command asserts directly; it had to be reified into a named test rather than command-checkable stdout.
- **M4 — Exit gate objectivity (4):** two of the seven AND-clauses ("nudge suppressed for the lifetime of the AgentLoop"; "updated after every `_handle_tool_calls()` return") are lifecycle invariants verifiable only indirectly through named tests. The prompt compensates by instructing per-clause evidence, so the dock is minor.

(All four prompts are unusually strong — explicit expected-files lists, concrete do-not enumerations, line-anchored mandatory reading, `git -C` / `grep -F` fallbacks, SHA-capture warnings, and a machine-checked 6-side-effect contract. None scored below 39.)

### Reconciled execution quality scorecards

| Milestone | Commit hygiene | Test growth | Gate honor | Divergence discipline | Log cleanliness | Implementation matches PLAN | Scope discipline | HANDOFF accuracy | Failure-path coverage | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| M1 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 45/45 |
| M2 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 45/45 |
| M3 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 4 | 44/45 |
| M4 | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 3 | 5 | 41/45 |

- **M3 — Failure-path coverage (4):** good edge coverage (failed read_file skipped, point-in-time snapshot consistency, newest-wins per-path eviction, empty-transcript compact), but the attachment-emission path is exercised mostly on well-formed snapshots; no test drives an empty/`<recent-files>`-colliding `content`.
- **M4 — HANDOFF accuracy (3):** the phantom-685 baseline / understated +19 delta (true: 670 → 704, +34). Independently verified by the main agent. Documentation-accuracy defect, not a gate failure.
- **M4 — Divergence discipline (4):** the cli.py/openai_cli.py wiring change pushes the src touch count to 6 (the SIZING-WAIVED ceiling). Disclosed and genuinely necessary (closure ownership), so a minor dock only.
- **M4 — Log cleanliness (4):** `logs/M4.log` contains a single line ("You've hit your session limit · resets 10:10pm") — the session was quota-truncated, so the rich gate-evidence M1–M3 logs carry is absent. The work itself landed correctly and is green at HEAD (704, mypy/ruff clean), so the milestone finished; the log is just not a clean record.

(M1–M3 executions are exemplary: one commit per milestone, every gate clause backed by named tests quoted in the logs, deviations openly documented, append-only HANDOFF/PROGRESS contracts honored verbatim.)

### Reconciled detail-level findings

- **M4 reports a phantom test baseline (685) and an understated delta (+19)** — `initiatives/current/PROGRESS.md` (M4 block) and `initiatives/current/HANDOFF.md:250-251` (commit `02f17f6`) — MEDIUM
  - **What**: HANDOFF/PROGRESS/commit-message claim M4 went "685 → 704 (+19)". Actual collected counts are M3-end (`646bf2c`) = 670 and M4 (`02f17f6`) = 704, so the true figures are baseline 670 and delta +34. No commit in `8f1d98f..HEAD` ever collected 685 tests (615→632→647→670→704). **Independently verified** via `git worktree` + `pytest --collect-only`.
  - **Why it matters**: the fact log the review consumes is wrong about both the starting count and the size of M4's contribution; a future reader cannot reconcile 670≠685, and the +19 claim hides 15 tests of real growth.
  - **Fix sketch**: correct the M4 PROGRESS block + HANDOFF §2 to "670 → 704 (+34)" and drop the "+19 after tightening" rationalization. No code change — the suite is green at 704. (Not auto-applied here: rewriting a milestone's own historical fact-log is outside the wrap agent's mandate; surfaced for human correction.)

- **Prepended attachment / nudge messages can produce consecutive same-role (user) API messages** — `src/simple_coding_agent/context.py:278-281` (M3 `_attachment_dicts` + M4 nudge prepend) — MEDIUM
  - **What**: `build()` prepends user-role attachment dicts and the user-role nudge dict AFTER `_normalize_messages` (the only same-role merge site) and AFTER the trim/orphan pass. When the first kept message is also user-role the payload front becomes `[user-attachment, (user-nudge,) user-kept, ...]` — adjacent user messages bypassing the same-role merge.
  - **Why it matters**: Anthropic's Messages API rejects/coerces consecutive same-role turns; OpenAI Chat Completions tolerates but may mis-handle them. The all-MockProvider suite never serializes to a real endpoint, so the 704 green tests cannot see this. HANDOFF §5 (a)/(b) already flags a needed live smoke run here.
  - **Fix sketch**: either run the prepended dicts back through a same-role merge before composing the final payload, or assert+document that the first kept message after a compact boundary is always assistant-role. Add a test building with a user-role first-kept message asserting no two adjacent user dicts.

- **`evaluate_snip_request([])` succeeds and triggers a no-op `replace_all`** — `src/simple_coding_agent/snip_tool_model.py` (`evaluate_snip_request` / tool fn) — LOW
  - **What**: an empty `message_uuids` list passes validation (the loop body never runs), returns `SnipOutcome(refused=False, removed_uuids=())`, and the tool fn calls `transcript.replace_all(messages)` returning `"Snipped 0 messages"`. The JSON schema requires the key but not `minItems: 1`.
  - **Why it matters**: a model emitting `snip_history({"message_uuids": []})` gets a success string and a pointless full-transcript rewrite rather than a corrective error, weakening the refusal feedback loop.
  - **Fix sketch**: add `"minItems": 1` to the schema, or short-circuit in the tool fn to raise `SnipRefusedError("snip refused: no message_uuids provided")` for an empty list; cover with a test.

- **M2 ancient-cleared eviction counts at message granularity (all-or-nothing per message)** — `src/simple_coding_agent/snip.py` `_cleared_messages` / `_delete_cleared_pair` (commit `70be001`) — LOW
  - **What**: Phase-3 token accounting sums whole-message estimates and deletes every cleared ToolResult in a targeted message at once, so a multi-cleared-result message can overshoot below threshold in one step.
  - **Why it matters**: harmless with the standard one-result-per-message shape; a future bundling producer would over-evict. **Already disclosed** as a known limitation in HANDOFF §2 (M2) — flagged LOW for completeness only.
  - **Fix sketch**: if bundled-result messages ever become possible, switch eviction accounting to per-ToolResult-block granularity; until then the HANDOFF note suffices.

## Auto-applied edits

- Tier A | `CLAUDE.md` | appended a new `### snip_tool_model.py` section to the Per-File Summaries (after `### trace.py`, before the `---` preceding the Implementation Roadmap) | trigger: "`src/` has a new `.py` file with at least one public symbol that is not yet in CLAUDE.md's per-file summary table" (`snip_tool_model.py`, 256 LOC, `__all__` lists 7 public symbols, absent from the summary table) | source: doc-curator candidate (HIGH), confirmed by main-agent inspection of `__all__`
- Tier B | `docs/DECISIONS/0002-coexisting-engine-and-model-snip.md` | new ADR capturing the coexisting engine + model-driven snip decision, uuid in-content wrapping, live-Transcript closure sharing, and attachment/nudge ordering | trigger: "HANDOFF.md Section 2 collectively contains ≥2 divergences AND ≥1 architectural, OR a single divergence touches >2 source files" (both clauses fire: M2 `SNIP_BOUNDARY` + M3 `FileSnapshot`/`ATTACHMENT` + M4 `snip_history`/`SnipNudge` are architectural; the M4 closure-ownership fix touches `cli.py`/`openai_cli.py`/`tool_registry_factory.py`/`context.py`) | source: doc-curator candidate (HIGH), confirmed by main-agent
- Tier B (index) | `docs/DECISIONS/README.md` | appended the `0002` index row | trigger: standard ADR-creation bookkeeping (RUNBOOK Step 3C ADR substep 8) | source: main-agent
- Tier B | `docs/snip-tool-model.md` | **NOT created (skipped)** | the subsystem-doc trigger fires mechanically (256 LOC, 7 symbols) but the module is a single file tightly coupled to the documented `snip.py` subsystem; a standalone doc would duplicate the Tier A CLAUDE.md summary + ADR-0002. doc-curator itself recommended folding in. | source: main-agent decision

## Proposed edits (need human review)

1. `README.md` (Console-scripts / flag prose, ~line 80) — Document the four new `simple-agent` flags (`--microcompact-keep-recent`, `--output-headroom`, `--compact-headroom`, `--min-session-tokens`) added in `cli.py` (M1). — why: README maintains no per-flag list for `simple-agent` (only prose naming `--verbose` / `--aggressive-thresholds`), so surfacing these requires rewriting existing prose, not appending a table row — the Tier A action has no append target.
   Trigger: Tier C "README.md Setup section needs reorganization".
   Suggested diff:
   ```diff
   - Both entry points support `--verbose` (stream `[trace] [<channel>] …` events to stderr) and `--aggressive-thresholds` (lower compact/snip/microcompact thresholds for demo-friendly behavior; prints a banner summarizing the preset).
   + Both entry points support `--verbose` (stream `[trace] [<channel>] …` events to stderr) and `--aggressive-thresholds` (lower compact/snip/microcompact thresholds for demo-friendly behavior; prints a banner summarizing the preset). The `simple-agent` REPL additionally accepts `--microcompact-keep-recent`, `--output-headroom`, `--compact-headroom`, and `--min-session-tokens` to override the PDF-aligned compaction thresholds.
   ```

2. `CLAUDE.md` "## Implementation Roadmap (Completed P1–P9)" — Add a roadmap entry for `ctx-mgmt-pdf-align` (M1–M4), mirroring the existing `observable-thresholds` / `P9 — M*` entries. — why: the roadmap is the historical changelog and this initiative belongs there, but the RUNBOOK Tier A rules explicitly forbid touching the Implementation Roadmap section; adding a bullet edits a protected section and requires human judgment on numbering/wording.
   Trigger: Tier C (closest match — roadmap editing is prose-level historical narrative outside the safe append surface; RUNBOOK does not permit auto-editing the Roadmap).
   Suggested addition (append as a new bullet at the end of the roadmap list):
   ```markdown
   - **ctx-mgmt-pdf-align initiative — M1–M4** (`8f1d98f`–`02f17f6`, 2026-05-23). Aligns the five-mechanism context pipeline with the PDF: M1 microcompact `keep_recent=5` + double-headroom autocompact threshold + LLM-default summarizer + 4 CLI flags; M2 engine snip orphan + ancient-cleared-pair deletion + `SNIP_BOUNDARY`; M3 recent-files snapshot + post-compaction `ATTACHMENT` re-injection (`FileSnapshot`, frozen `CompactSummary`); M4 model-driven `snip_history` tool + `<msg uuid="...">` wrap + 10k-token `SnipNudge`. See ADR-0002. pytest 615 → 704 (+89).
   ```

3. `initiatives/_archive/2026-05-ctx-mgmt-pdf-align/PROGRESS.md` (M4 block) and `HANDOFF.md` §2 (M4) — Correct the phantom test baseline. — why: rewriting a milestone's own historical fact-log is outside the wrap agent's mandate (append-only contract), so this is proposed rather than auto-applied.
   Trigger: Tier C (edits existing historical records).
   Suggested diff:
   ```diff
   - - **tests**: 685 → 704 (+19; ... actual delta is +19 after one assertion in test_context.py was tightened ...)
   + - **tests**: 670 → 704 (+34; +16 test_snip_tool_model.py [new], +12 test_loop.py, +6 test_context.py, +1 test_agent_integration.py)
   ```

## Phase 2C: Wrap-up actions taken

- **Archived** the initiative: `git mv initiatives/current initiatives/_archive/2026-05-ctx-mgmt-pdf-align`, then recreated the empty active slot (`mkdir initiatives/current && touch initiatives/current/.gitkeep`).
- **Rewrote `NOW.md`**: active initiative = none; last completed = ctx-mgmt-pdf-align (615 → 704, final commit `02f17f6`), with links to this REVIEW.md and OWNER_BRIEF.zh-CN.md. Preserved the "How to start a new initiative" section verbatim.
- **Updated `initiatives/README.md`**: Active table set to _(none)_; appended the archived row `2026-05-ctx-mgmt-pdf-align | complete | 2026-05-23 | M1 → M4 | 02f17f6`. Table schema left unchanged (REVIEW.md + OWNER_BRIEF.zh-CN.md are discoverable inside the archive folder).
- **Applied Tier A/B doc edits** (see `## Auto-applied edits`): CLAUDE.md `### snip_tool_model.py` summary; new ADR `docs/DECISIONS/0002-coexisting-engine-and-model-snip.md` + its index row.
- **Wrote** `logs/review.log` (terse session summary).
- **Committed** everything as a single `[ctx-pdf/wrap]` commit; verified `git status --short` is empty afterward.

## Owner brief

The decision-maker-facing Chinese owner brief lives in
[`OWNER_BRIEF.zh-CN.md`](./OWNER_BRIEF.zh-CN.md). Read that file for
"what was built / how to demo it / before-after / how to talk about it".

## Post-review follow-up (2026-05-24, user-directed)

After reading this review the owner directed fixes for all three surfaced
findings. Quality after the follow-up: **pytest 704 → 707**, mypy clean (22
files), ruff clean.

- **Finding 2 (consecutive same-role payload) — RESOLVED, contract changed.**
  The owner chose Anthropic-compatibility over the prior OpenAI-only adjacency.
  `context.build()` now runs a final `_coalesce_same_role()` pass (new helper,
  sharing a factored-out `_merge_content`) so prepended attachments + nudge +
  a user-role first-kept message merge into one user message preserving
  `[*attachments, nudge, *kept]` order. Three pinning tests were rewritten and
  one added (`test_build_coalesces_consecutive_same_role_into_anthropic_compatible`).
  NOTE: this supersedes the M4 HANDOFF §4 invariant that pinned *separate*
  `[*attachments, nudge, *kept]` messages — order is preserved, but they are
  now coalesced.
- **Finding 3 (empty `snip_history` list) — RESOLVED.** `evaluate_snip_request`
  now refuses an empty list (`reason="no message_uuids provided"`); the tool fn
  raises `SnipRefusedError` (is_error). Added `"minItems": 1` to the tool schema
  (the exact-schema test was updated accordingly). +2 tests.
- **Finding 1 / Proposed edit #3 (phantom 685) — APPLIED.** Archived
  `PROGRESS.md` + `HANDOFF.md` M4 records corrected to `670 → 704 (+34)` with a
  dated marker. Real per-file deltas verified via `git worktree` + collect:
  +16 snip_tool_model [new], +12 loop, +6 context, +0 agent_integration (the
  original's "+1 agent_integration" was also wrong — that file is 12→12).
- **OpenAI live smoke run — DONE (via DashScope `qwen3.6-plus`).** The `.env`
  carries `DASHSCOPE_API_KEY` + `OPENAI_BASE_URL`, so the OpenAI-compatible path
  was exercised live:
  - **Smoke 1:** one-shot `read_file` task — the `<msg uuid="...">` wrap survived
    serialization; the model read through it correctly.
  - **Smoke 2:** `--aggressive-thresholds` REPL — full compaction + recent-file
    re-injection fired live; the coalesced (P1) attachment payload was accepted
    with no API error; the model answered a post-compaction question whose answer
    lived only in the re-attached snapshot (byte 6781, beyond the externalize
    preview).
  - **Smoke 3 (model-driven snip, audit item a):** required a new flag —
    `--snip-nudge-growth-tokens` (added this round to both CLIs; `preset_key=None`
    so `--aggressive-thresholds` does NOT touch it, because aggressive compaction
    resets the nudge window every step). A 2-turn REPL with `--snip-nudge-growth-tokens 500`
    and the default roomy budget armed the nudge; the model emitted a valid
    `snip_history` call and the executor returned `"Snipped 2 messages"` against the
    live transcript. Confirmed by inspecting the saved session JSON
    (`"name": "snip_history"` + `Snipped 2 messages`, no refusal).
  - All audit items (a)/(b) and findings 1/2/3 are now validated live.
- **Proposed edits #1 (README flags) and #2 (CLAUDE.md roadmap entry)** remain
  open for human review (not in scope of this follow-up).
