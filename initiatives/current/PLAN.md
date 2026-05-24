---
slug: ctx-mgmt-demo
commit_prefix: ctx-demo

milestones:
  M1:
    name: cli-flags-microcompact-minutes-and-max-turns
    phase_ids: [F1]
    exit_gate: |
      `simple-agent --help` AND `simple-agent-openai --help` both list
      `--microcompact-minutes`. `simple-agent-openai --help`
      additionally lists `--max-turns`. `pytest -q` is green with at
      least 3 new test cases covering the flags.
    notes: |
      Two additive CLI flags. No new abstractions.

      --microcompact-minutes N (both cli.py and openai_cli.py):
        - Plumbs to MicroCompactor(threshold_minutes=N) via the
          existing three-state precedence (explicit flag > the
          _AGGRESSIVE_THRESHOLDS preset > built-in default of 60).
          Pattern: see how --microcompact-keep-recent is wired
          through cli._resolve_threshold in cli.py; mirror for
          openai_cli if not already there.
        - The aggressive preset already sets microcompact_minutes=1.
          The new flag exposes the same lever directly.
        - N=0 must work: it means "any age qualifies" so microcompact
          fires on the next turn after a compactable tool_result.
          observable-thresholds-harden M2 added a
          MicroCompactor(threshold_minutes<1) guard test — check it
          first. If 0 trips the guard, either relax the guard to
          N<0 OR set the flag minimum to 1 (and update M2 scenario
          03 to use --microcompact-minutes 1 + a brief sleep).

      --max-turns N (openai_cli.py REPL only):
        - REPL exits cleanly after N user turns, taking the same
          shutdown path as /exit (dump SessionMemory, save session
          if one was loaded, exit 0).
        - Counter checked at the top of the read loop in
          _drive_repl_session (or the openai_cli equivalent) before
          input() blocks.
        - Purpose: deterministic finish so M2 can capture artifacts
          without manual /exit.

      Source files touched (≤ 3):
        - src/simple_coding_agent/cli.py
        - src/simple_coding_agent/openai_cli.py
        - (no src change expected to compact.py — MicroCompactor
           already takes threshold_minutes)

      Tests (at least 3 new cases):
        - tests/test_cli.py: --microcompact-minutes parsed and
          propagates to MicroCompactor.threshold_minutes.
        - tests/test_openai_cli.py: --microcompact-minutes parsed
          and propagates.
        - tests/test_openai_cli.py (or test_openai_cli_repl.py):
          --max-turns N causes clean exit after exactly N turns
          (scripted stdin or fake provider).

  M2:
    name: capture-real-api-artifacts-for-3-scenarios
    phase_ids: [F2]
    exit_gate: |
      `python-replica/demo/_artifacts/` contains three subdirectories
      (01_tool_result_management/, 02_full_compact/,
      03_microcompact/), each with transcript.txt, trace.stderr,
      metrics.json, stats_output.txt. The metrics.json values
      satisfy:
        01 → snip_invocations >= 1 AND externalized_bytes > 0
        02 → full_compacts >= 1
        03 → microcompact_invocations >= 1
      All three captures use the real DashScope API via the existing
      `python-replica/.env`. No env.sample created. No notebook .md
      files written yet (those land in M3). The model actually used
      for each scenario is recorded in that scenario's
      stats_output.txt header (so a re-runner can tell which model
      produced which artifact).
    notes: |
      Pure side-effect milestone. Run real API, write artifacts.

      Provider + credentials:
        simple-agent-openai consumes the existing python-replica/.env,
        which is already populated with DASHSCOPE_API_KEY,
        OPENAI_BASE_URL (DashScope compatible-mode), and
        SIMPLE_AGENT_MODEL. DO NOT create env.sample. DO NOT ask the
        user for credentials.

      Model is swappable — quota-exhaustion playbook:
        The default model in .env may exhaust its quota mid-capture
        (free-tier limits, daily caps, etc.). On any quota /
        rate-limit error that is NOT recoverable by waiting <60s:
          1. Stop the failing capture immediately (do NOT retry the
             same model — wastes more spend).
          2. Edit python-replica/.env, change SIMPLE_AGENT_MODEL to
             one of the supported alternatives below (all reachable
             through the same OPENAI_BASE_URL):
                qwen3-coder-plus-2025-09-23
                glm-5
                deepseek-v3.2
                qwen-plus-latest
                qwen-long-latest
          3. Restart that scenario's capture.
          4. Record which model produced which artifact in that
             scenario's stats_output.txt header (e.g., a leading
             `# model: <name>` line) so M3's notebook can show the
             real model used. Counter-level exit_gate assertions
             are model-agnostic — they pin behavior, not text.
        If two consecutive models from the list also fail with quota
        errors, STOP and surface this to the owner rather than
        cycling through all five.

      Capture pattern: mirror examples/visibility_full_demo.py
      (SDK-based driver, not shell pipe — REPL stdin scripting is
      fragile). Reuse its _parse_trace_events helper. A single
      generic driver that takes per-scenario config is preferred over
      three near-duplicates; put it under demo/_scripts/ (with a
      leading underscore so it's clearly internal, not a demo
      itself).

      Per-scenario configs (the agent picks the exact tool-call
      script that triggers the named counters; these are guidance):
        01 (snip + externalize):
          flags: --repl --verbose --max-turns 6 --aggressive-thresholds
          script: read_file(A), read_file(A) repeat (→ snip),
                  read_file(big_B large enough to externalize under
                  aggressive's max_inline_chars=2000), /stats, /exit
        02 (full compact):
          flags: --repl --verbose --max-turns 6 --aggressive-thresholds
          script: accumulate enough tool_result tokens to cross the
                  aggressive threshold (max_context_tokens=4000 *
                  compact_threshold=0.2 ≈ 800 tokens used). /stats; /exit
        03 (microcompact):
          flags: --repl --verbose --max-turns 4 --aggressive-thresholds
                 --microcompact-minutes 0  (from M1)
          script: read_file(A); any input on turn 2 to trigger
                  microcompact; /stats; /exit

      Reactive compact and any memory mechanism are explicitly OUT.

      Cost guardrail: total < $0.20 across all 3 captures. If any
      single capture exceeds $0.10, STOP and report rather than
      retry-burning more API spend.

      Per-scenario artifact layout under demo/_artifacts/<scenario>/:
        - transcript.txt   (full message history captured by driver)
        - trace.stderr     (raw [trace] event stream)
        - metrics.json     (MetricsCollector serialized)
        - stats_output.txt (raw /stats stdout; first line is
                            `# model: <SIMPLE_AGENT_MODEL value>`)

      Commit the artifacts and the driver under demo/. They ARE the
      demo evidence.

  M3:
    name: write-3-notebooks-and-readme
    phase_ids: [F3]
    exit_gate: |
      `python-replica/demo/` contains:
        - README.md (links the 3 notebooks; references
          examples/stress_demo.py for reactive compact with
          rationale; documents the swappable-model fallback list)
        - 01_tool_result_management.md
        - 02_full_compact.md
        - 03_microcompact.md
      Each notebook embeds at least 5 lines of captured output from
      its corresponding `_artifacts/` folder, includes
      file:line source references for each demoed mechanism, shows
      the exact command line that produced the artifacts, and names
      the model that actually produced them (read from
      stats_output.txt header).
      No src/ changes, no new tests, no additional real-API spend.
    notes: |
      Pure docs milestone. M2's artifacts already exist; M3 reads
      them and writes markdown.

      Per-notebook structure:
        # Title + one-paragraph goal
        ## Setup (env, exact command line used in M2, model name
                  read from the artifact's stats_output.txt header)
        ## Step-by-step
          - numbered, with embedded ``` blocks: $ command, then
            the relevant captured output (don't paste the entire
            artifact — pick the demonstrative lines)
        ## What to look for
          - which [trace] channel lines, which /stats counters,
            and what they prove
        ## Source mapping
          - file:L references into src/simple_coding_agent/...
            for each demoed mechanism

      Embed style: fenced blocks, language-tagged. Use ```text for
      trace stderr, ```json for metrics, ```console for transcript
      excerpts.

      README.md must:
        - One-line summary of each notebook.
        - Note that _artifacts/ is one canonical run; re-runs vary
          in exact text but counter-level assertions hold.
        - Point reactive-compact readers to
          examples/stress_demo.py with the rationale that reactive
          compact is provider-independent error recovery — the
          mock demo is the right surface for that mechanism.
        - List env vars consumed (DASHSCOPE_API_KEY,
          OPENAI_BASE_URL, SIMPLE_AGENT_MODEL) and point at the
          existing python-replica/.env (NOT env.sample).
        - Document the swappable-model fallback: list the
          alternatives (qwen3-coder-plus-2025-09-23, glm-5,
          deepseek-v3.2, qwen-plus-latest, qwen-long-latest) and
          tell re-runners to switch the .env's SIMPLE_AGENT_MODEL
          if their default's quota is dead.
---

> Bootstrapped on 2026-05-25. Baseline commit: `9ba662bf65e45d08949d4524203773a63bf36902`. Baseline pytest: 816 passing.

# Goal

Ship three notebook-style markdown demos under `python-replica/demo/`
that exercise the context-management mechanisms (snip, externalize,
full compact, microcompact) against the real DashScope API (via
`simple-agent-openai`) and embed captured `[trace]` events,
`/stats` counters, and transcript excerpts inline. Reviewers can
read the demos without running them and can re-run them locally
with the existing `.env` (and, if their default model's quota is
exhausted, by swapping in one of the documented alternatives).
This complements `examples/visibility_full_demo.py` (a single
combined real-API run) with per-mechanism walkthroughs and
explanatory prose.

The memory-module demo is deferred — the memory layer needs further
strengthening before a public demo is warranted.

# Background / motivation

The replica has 711 pytest cases proving correctness of the
context-management pipeline, but only one real-API artifact-capturing
example exists (`examples/visibility_full_demo.py`) and it is a
single combined run rather than a per-mechanism explanation. A
reviewer reading the repo today cannot easily map "which lever
triggers which observable event." Two new CLI flags (M1) close the
gap: `--microcompact-minutes` lets microcompact fire deterministically
without waiting 60+ seconds in a notebook; `--max-turns` lets a
real-API REPL exit cleanly so artifacts can be captured.

# Design sketch

**M1 — two additive flags, no new abstractions.** Both flags follow
existing precedence patterns. `MicroCompactor` already accepts
`threshold_minutes`; `--microcompact-minutes` just exposes it on the
CLI. `--max-turns` is a counter in the REPL read loop.

**M2 — real-API captures only.** Three scenarios, each driven by an
internal capture script that mirrors `examples/visibility_full_demo.py`
(SDK-based, not shell-pipe). The aggressive-thresholds preset does
most of the work; `--microcompact-minutes 0` (from M1) makes scenario
03 instantaneous. The model is read from .env and is swappable per
the quota-exhaustion playbook in M2 notes.

**M3 — docs only.** Three markdown files plus README. No src
changes. Each notebook embeds carefully-chosen lines from M2's
artifacts and names the model that produced them.

# Risks / known unknowns

- **API spend.** Per scenario < $0.10 on a typical DashScope-tier
  model; per-run hard cap in M2 notes prevents burn-on-retry.
- **Model quota exhaustion.** The default model in .env may run dry
  mid-capture. M2 notes carry a swappable-model playbook with five
  documented alternatives; if two consecutive alternates also fail,
  M2 must stop and surface to the owner rather than cycle through
  all five.
- **Cross-model determinism.** Different models produce different
  trace text and transcript content. M2 records which model each
  scenario used (in stats_output.txt header); M3 surfaces it in
  each notebook's Setup. Counter-level exit gates remain
  model-agnostic.
- **Non-determinism within a single model.** Real-LLM output varies
  run-to-run. Notebooks pin counter-level assertions
  (`full_compacts >= 1`) rather than verbatim text. The captured
  `_artifacts/` are one canonical run.
- **`--microcompact-minutes 0` vs existing guard.** observable-
  thresholds-harden M2 added a `MicroCompactor(threshold_minutes<1)`
  guard test. M1 must check this first and either relax the guard
  or use 1+brief sleep in M2 scenario 03.
# Out of scope (this initiative)

- Memory module demos (deferred until memory layer is strengthened).
- Anthropic-native provider (replica has MockProvider +
  OpenAIProvider only).
- Reactive compact real-API demonstration (impractical: requires
  exceeding the model's window for real spend; pointer to
  `examples/stress_demo.py` instead).
- `--seed-memory`, `--memory-dir`, `/recall`,
  `--print-system-prompt` flags (memory-related; deferred).
- `env.sample` (the existing `.env` is already configured).
- New context-mgmt mechanisms; this initiative purely surfaces
  what P1–P9 + observable-thresholds + ctx-mgmt-pdf-align already
  shipped.
- Adding new models to the supported list. The five alternates in
  M2 notes are the complete set for this initiative.

# Anything else

The existing `.env` at `python-replica/.env` is pre-configured with
`DASHSCOPE_API_KEY`, `OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1`,
and a `SIMPLE_AGENT_MODEL` value. M2 reads it directly — no
re-prompting, no env.sample.

**Model is swappable.** If the default model's quota dies during a
capture, the operator (or the M2 agent, per the playbook in M2
notes) may edit `.env` and change `SIMPLE_AGENT_MODEL` to any of
the supported alternatives. All five are reachable through the
same `OPENAI_BASE_URL` value already in `.env`:

  - qwen3-coder-plus-2025-09-23
  - glm-5
  - deepseek-v3.2
  - qwen-plus-latest
  - qwen-long-latest

The model actually used for each scenario lands in that scenario's
`stats_output.txt` header (`# model: <name>`) so M3's notebook can
name it.

`examples/visibility_full_demo.py` is the structural reference for
the artifact format and the SDK-based capture pattern. M2 should
reuse its `_parse_trace_events` helper and `_new_run_dir`
collision-avoidance pattern rather than reinventing.

`python-replica/demo/` exists as an empty directory and is reserved
for this initiative. M2 populates `demo/_artifacts/<scenario>/` and
`demo/_scripts/`; M3 populates `demo/README.md` and the three
notebook `.md` files.
