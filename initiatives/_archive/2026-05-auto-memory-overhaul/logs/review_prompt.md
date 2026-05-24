<!--
PROMPT for the script-spawned review + wrap-up session.

automation/scripts/run_all_milestones.sh invokes one final
`claude --remote-control` after all milestones pass their exit gate.
The script substitutes auto-memory-overhaul, auto-mem,
2026-05-auto-memory-overhaul, and 6aed9ec6864aebf7cd41a6b3b5859e9ff87dde6d (4 tokens) before piping
this file as stdin.

This is the MULTI-AGENT version: the main review session acts as
orchestrator. It runs code-reviewer + doc-curator-candidate-finder
in parallel as READ-ONLY subagents, reconciles their outputs, applies
Tier A/B doc edits itself, then runs demo-narrator after reconciliation
so the Chinese owner brief can include the findings that matter.

Outputs:
- REVIEW.md — English archive review for cross-initiative comparison.
- OWNER_BRIEF.zh-CN.md — Chinese owner-facing brief for understanding,
  demo, before/after, and interview/resume storytelling.

Phase 2C archives the initiative, rewrites NOW.md, updates index files,
commits the wrap result, then stays alive on --remote-control so the
human can attach and ask follow-up questions.

Comment blocks (HTML comments) are guidance and should NOT appear in
REVIEW.md or OWNER_BRIEF.zh-CN.md.
-->

# Phase 2B + 2C — Multi-agent review + wrap-up for `auto-memory-overhaul`

You are the **MAIN REVIEW AGENT** for the `auto-memory-overhaul`
initiative. Every milestone has already produced its commit. Your job
is to perform a staged multi-agent review, archive the initiative, and
remain available for human follow-up via `--remote-control`.

Your work has 4 acts:

1. **Phase 2B preflight**: verify every milestone commit exists and the
   final quality gates are green.
2. **Phase 2B multi-agent review**:

   * Stage A: spawn 2 READ-ONLY subagents in parallel:
     `code-reviewer` and `doc-curator-candidate-finder`.
   * Stage B: reconcile their outputs yourself. Do not blindly paste
     contradictory or duplicated findings.
   * Stage C: apply Tier A/B doc edits yourself, then spawn
     `demo-narrator` with the reconciled findings so the Chinese owner
     brief reflects the important code/doc findings.
3. **Phase 2C wrap-up**: create `REVIEW.md` and
   `OWNER_BRIEF.zh-CN.md`, archive `initiatives/current/`, rewrite
   `NOW.md`, update `initiatives/README.md`, write `review.log`, and
   commit everything as `[auto-mem/wrap]`.
4. **Stay alive on `--remote-control`**. After the wrap-gate verifies,
   print the exact attach message in Step 11. Do NOT `/exit`. The
   session terminates only when the user `/exit`s manually.

There is no user available during Phase 2B / 2C. Stop only on a clear
quality failure: missing milestone commit, pytest red, mypy red, or ruff
red. After Phase 2C, the user attaches via browser extension or Claude
desktop app to ask follow-up questions in any language.

## Mandatory reading — main agent reads this FIRST

Read these before spawning any subagents:

1. `python-replica/automation/RUNBOOK.md` — your role is documented in
   Phase 2B + 2C. Read the section "Doc-update tiers (used by Step 6)"
   carefully because YOU, not the doc-curator subagent, will apply Tier
   A/B edits after reconciliation.
2. `python-replica/initiatives/current/PLAN.md` — the original brief.
3. `python-replica/initiatives/current/config.yaml` — milestone table.
4. Every `python-replica/initiatives/current/prompts/M{N}.md` —
   per-milestone prompts.
5. Every `python-replica/initiatives/current/logs/M{N}.log` — raw run
   logs.
6. `python-replica/initiatives/current/HANDOFF.md` — terminal state.
7. `python-replica/initiatives/current/PROGRESS.md` — per-milestone log.

You do NOT need to read every source file hunk before spawning Stage A
subagents. The `code-reviewer` subagent does the full source/test diff
review. You need enough understanding to coordinate, reconcile, write a
sensible summary, and safely apply doc edits.

---

# Phase 2B — Review

## Step 1: Verify completion

For every M{N} in `config.yaml`:

```bash
git -C python-replica log 6aed9ec6864aebf7cd41a6b3b5859e9ff87dde6d..HEAD --oneline | grep -F "[auto-mem/M{N}]"
```

This must return at least one match. The `6aed9ec6864aebf7cd41a6b3b5859e9ff87dde6d..HEAD`
range restricts the search to THIS initiative's commits, preventing
false positives from prior archived initiatives that reused the same
`commit_prefix`. `6aed9ec6864aebf7cd41a6b3b5859e9ff87dde6d` was substituted by the shell
script from `initiatives/current/config.yaml` during Phase 1.

If any milestone is missing its commit:

1. STOP.
2. Write `initiatives/current/REVIEW.md` with only a `# BLOCKED` section
   explaining which milestone is missing and why.
3. Do NOT spawn subagents.
4. Do NOT create `OWNER_BRIEF.zh-CN.md`.
5. Do NOT run Phase 2C archive / wrap-up steps.

## Step 2: Snapshot final numbers

```bash
cd python-replica
pytest --tb=no -q       # record total passing
mypy src/               # record status
ruff check .            # record status
```

If pytest is red OR mypy is red OR ruff is red:

1. STOP.
2. Write `initiatives/current/REVIEW.md` with only a `# BLOCKED` section
   quoting the failing output.
3. Do NOT spawn subagents.
4. Do NOT create `OWNER_BRIEF.zh-CN.md`.
5. Do NOT run Phase 2C archive / wrap-up steps.

Record:

* final pytest count
* baseline pytest count, if available from PROGRESS.md / PLAN.md
* pytest delta
* mypy status
* ruff status
* final commit SHA before wrap
* number of commits in `6aed9ec6864aebf7cd41a6b3b5859e9ff87dde6d..HEAD`
* start/end dates from first and last initiative commits

---

## Step 3A: Spawn 2 READ-ONLY subagents in parallel

In a **SINGLE message**, issue **2 `Agent` tool calls**:

1. `code-reviewer`
2. `doc-curator-candidate-finder`

They must run in parallel. Wait for both to return before proceeding.

For each subagent:

* `subagent_type` = `"general-purpose"`
* `description` = the short label given below
* `prompt` = the literal markdown text between
  `----- BEGIN PROMPT[<role>] -----` and
  `----- END PROMPT[<role>] -----` for that role, with the 4
  `{{...}}` tokens already substituted by the shell script.

Important: **both Stage A subagents are read-only**. They must not edit,
write, stage, commit, delete, move, or archive any file. The MAIN REVIEW
AGENT is the only writer.

---

## Subagent 1: `code-reviewer`

`description`: `"code-review-for-auto-memory-overhaul"`

----- BEGIN PROMPT[code-reviewer] -----

You are the **code-reviewer subagent** for the `auto-memory-overhaul`
initiative. You evaluate prompt quality, execution quality, and concrete
code correctness risks for this initiative's diff.

You are READ-ONLY. Do not modify any file.

## §Role

Audit every milestone on two scorecard axes:

1. **Prompt quality** — how well-written was each `prompts/M{N}.md`?
   Was it clear, complete, scope-aligned, constraint-specific, and
   exit-ritual-correct?
2. **Execution quality** — how well did the milestone agent execute
   against the prompt and PLAN? Did the commit match the plan, were
   tests meaningful, were failures/edge paths covered, and did it stay
   in scope?

Additionally, surface **detail-level findings**: concrete bugs,
correctness risks, missing edge cases, fragile patterns, misleading
claims, or implementation-depth gaps introduced by the initiative diff.

## §Inputs

Read in this order before scoring:

1. `python-replica/initiatives/current/PLAN.md`
2. `python-replica/initiatives/current/config.yaml`
3. Every `python-replica/initiatives/current/prompts/M{N}.md`
4. Every `python-replica/initiatives/current/logs/M{N}.log`
5. `python-replica/initiatives/current/HANDOFF.md` Section 2
6. `python-replica/initiatives/current/PROGRESS.md`
7. `git -C python-replica log 6aed9ec6864aebf7cd41a6b3b5859e9ff87dde6d..HEAD --oneline`
8. `git -C python-replica diff 6aed9ec6864aebf7cd41a6b3b5859e9ff87dde6d..HEAD -- src/ tests/`
9. Each milestone's individual commit:

   * `git -C python-replica show <commit> --stat`
   * selected hunks from `git -C python-replica show <commit>`

## §Output schema

Return ONE markdown block in EXACTLY this shape. The main agent will
reconcile and splice it into `REVIEW.md`.

```markdown
## Phase 2B-3: Prompt quality scorecards

For each `prompts/M{N}.md`, score on 8 dimensions (1-5 each):

| Milestone | Clarity | Completeness | Scope alignment | Constraint specificity | Exit-ritual correctness | Out-of-scope enumeration | Mandatory reading completeness | Exit gate objectivity | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| M1 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 40/40 |
| M2 | ... | ... | ... | ... | ... | ... | ... | ... | ... |

For each row whose total < 36/40, add one explanatory bullet beneath
the table explaining why a dimension was docked.

## Phase 2B-4: Execution quality scorecards

For each milestone, score on 9 dimensions (1-5 each):

| Milestone | Commit hygiene | Test growth | Gate honor | Divergence discipline | Log cleanliness | Implementation matches PLAN | Scope discipline | HANDOFF accuracy | Failure-path coverage | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| M1 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 45/45 |
| M2 | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |

Add explanatory bullets for any row whose total < 40.5/45.

## Detail-level findings

List concrete bugs / correctness risks / fragile patterns surfaced by
reading the diff. Bullet shape:

- **<short title>** — `<file>:<line>` — <severity: HIGH | MEDIUM | LOW>
  - **What**: <1-2 sentences describing the issue>
  - **Why it matters**: <1 sentence>
  - **Fix sketch**: <1-2 sentences>

If no detail findings: write
"(none — no detail-level issues found)".
```

## §Scoring dimensions

Prompt quality dimensions:

| Dimension                      | What to look for                                                              |
| ------------------------------ | ----------------------------------------------------------------------------- |
| Clarity                        | Can a fresh session execute this without ambiguity?                           |
| Completeness                   | Are required sections present and substantively filled?                       |
| Scope alignment                | Do scope + exit gate match PLAN's milestone entry?                            |
| Constraint specificity         | Are TDD / file-limit / no-`-A` / no-unrelated-refactor requirements explicit? |
| Exit-ritual correctness        | Does the prompt enforce the expected milestone exit ritual?                   |
| Out-of-scope enumeration       | Does it list concrete do-not items, not just generic disclaimers?             |
| Mandatory reading completeness | Does it list all required mandatory reads for the milestone?                  |
| Exit gate objectivity          | Is the exit gate objectively verifiable by command output?                    |

Execution quality dimensions:

| Dimension                   | What to look for                                                                |
| --------------------------- | ------------------------------------------------------------------------------- |
| Commit hygiene              | Subject matches `[auto-mem/M{N}]`; body explains why.                  |
| Test growth                 | Did pytest grow as expected? Were new tests meaningful?                         |
| Gate honor                  | mypy + ruff stayed clean.                                                       |
| Divergence discipline       | Deviations from PLAN are explained in HANDOFF Section 2.                        |
| Log cleanliness             | No unexplained errors / warnings / retries in milestone logs.                   |
| Implementation matches PLAN | Diff actually delivers the planned behavior, not just passing tests.            |
| Scope discipline            | Touched files match expected files + tests + required bookkeeping.              |
| HANDOFF accuracy            | Claimed behavior/files/tests match actual diff and PROGRESS.md.                 |
| Failure-path coverage       | Tests include invalid input, edge cases, or failure paths, not only happy path. |

## §Constraints

* Do NOT modify any file.
* Do NOT propose documentation edits except when a code finding depends
  on a misleading document claim; even then, phrase it as a risk, not as
  a doc-curator proposal.
* Do NOT write Chinese summaries or demo walkthroughs.
* Do NOT invent new scorecard dimensions.
* Cite every detail finding with `<file>:<line>` or commit SHA.
* A milestone whose new tests are all happy-path should be flagged under
  Failure-path coverage and, if meaningful, as a LOW or MEDIUM detail
  finding.
* Be strict about implementation depth. Passing tests are evidence, not
  proof.

----- END PROMPT[code-reviewer] -----

---

## Subagent 2: `doc-curator-candidate-finder`

`description`: `"doc-curator-candidates-for-auto-memory-overhaul"`

----- BEGIN PROMPT[doc-curator-candidate-finder] -----

You are the **doc-curator-candidate-finder subagent** for the
`auto-memory-overhaul` initiative. You identify which project docs may
need syncing because of this initiative's production-code diff.

You are READ-ONLY. Do not modify any file. Do not apply Tier A/B edits.
The MAIN REVIEW AGENT will reconcile your candidate list and apply any
approved Tier A/B edits itself.

## §Role

Classify doc-change candidates into three tiers per the RUNBOOK section
"Doc-update tiers (used by Step 6)":

* Tier A candidates: safe append-only mechanical edits.
* Tier B candidates: new file creations such as subsystem docs or ADRs.
* Tier C proposals: changes requiring rewrite, deletion, reorganization,
  or subjective human judgment.

Your output is advisory. The main agent is responsible for final
selection, edits, staging, and commit.

## §Inputs

1. `python-replica/automation/RUNBOOK.md` — read section
   "Doc-update tiers (used by Step 6)" verbatim.
2. `git -C python-replica diff 6aed9ec6864aebf7cd41a6b3b5859e9ff87dde6d..HEAD --stat -- src/ pyproject.toml`
3. `git -C python-replica diff 6aed9ec6864aebf7cd41a6b3b5859e9ff87dde6d..HEAD --name-only -- src/ pyproject.toml`
4. `git -C python-replica diff 6aed9ec6864aebf7cd41a6b3b5859e9ff87dde6d..HEAD -- src/ pyproject.toml`
5. `python-replica/initiatives/current/HANDOFF.md` — Section 2 design
   decisions / deviations from PLAN.
6. `python-replica/initiatives/current/PLAN.md`
7. `python-replica/CLAUDE.md`
8. `python-replica/README.md`
9. `python-replica/docs/` if it exists.
10. `python-replica/automation/templates/subsystem_doc.md`
11. `python-replica/automation/templates/adr.md`

## §Output schema

Return ONE markdown block in EXACTLY this shape. The main agent will
reconcile it, then apply approved Tier A/B edits itself.

````markdown
## Doc-update candidates

### Tier A candidates — safe append-only

If any Tier A candidate exists, list one bullet per candidate:

- Tier A candidate | `<target file>` | <one-line candidate edit> | trigger: <exact RUNBOOK Tier A rule> | confidence: <HIGH | MEDIUM | LOW>
  - Suggested append location: <section / line anchor>
  - Suggested appended text:
    ```markdown
    <exact append-only text>
    ```

If no Tier A candidate exists, write:

- Tier A candidate | (none) | no Tier A trigger matched | reason: <one-line reason>

### Tier B candidates — new files

If any Tier B candidate exists, list one bullet per candidate:

- Tier B candidate | `<new file path>` | <one-line file purpose> | trigger: <exact RUNBOOK Tier B rule> | confidence: <HIGH | MEDIUM | LOW>
  - Source evidence: <HANDOFF / PLAN / diff reference>
  - Template to use: `<template path>`
  - Placeholder values:
    - `{{placeholder}}`: <value>
  - If creating ADR: proposed ADR title = `<title>`; proposed slug = `<slug>`

If no Tier B candidate exists, write:

- Tier B candidate | (none) | no Tier B trigger matched | reason: <one-line reason>

### Tier C proposals — human review only

For every Tier C candidate:

1. `<file>:<line-or-section>` — <what to change> — why: <reason>
   Trigger: <exact RUNBOOK Tier C rule>
   Suggested diff:
   ```diff
   - <old line>
   + <new line>
````

If no Tier C candidates exist, write:

"(none — no proposed edits)".

````

## §Constraints

- Do NOT modify any file.
- Do NOT score code quality.
- Do NOT write Chinese summaries or demo walkthroughs.
- Every candidate must cite a specific RUNBOOK trigger row.
- Tier A must be safe and append-only. If unsure, mark confidence LOW or
  downgrade to Tier C.
- Tier B should be moderately aggressive, but still only as a candidate.
  The main agent decides whether to actually create files.
- Never propose editing the first 10 lines of `README.md`.
- Never propose editing the "Implementation Roadmap" section of
  `CLAUDE.md` unless RUNBOOK explicitly permits it. Prefer Tier C if
  uncertain.
- If a Tier B target path already exists, say so and recommend either a
  Recent changes append candidate or a Tier C proposal.

----- END PROMPT[doc-curator-candidate-finder] -----

---

## Step 3B: Reconcile Stage A outputs

After `code-reviewer` and `doc-curator-candidate-finder` both return,
perform reconciliation BEFORE writing files or launching demo-narrator.

Create an internal reconciliation note with these decisions:

1. **Final code findings**
   - Deduplicate overlapping findings.
   - Preserve all HIGH findings unless clearly unsupported.
   - If severity seems inflated or understated, adjust severity and
     explain why in `REVIEW.md`.
   - If evidence is weak, mark the finding as "uncertain" rather than
     stating it as fact.

2. **Final prompt/execution scorecards**
   - Use code-reviewer's scorecards as the source of truth unless you
     find an obvious contradiction with mandatory files.
   - Do not silently edit scorecard numbers. If you change them, add a
     short note in `REVIEW.md` explaining the correction.

3. **Final doc-update decisions**
   - For each Tier A candidate, decide APPLY / DOWNGRADE TO TIER C / SKIP.
   - For each Tier B candidate, decide CREATE / DOWNGRADE TO TIER C / SKIP.
   - For each Tier C candidate, decide INCLUDE / SKIP.
   - Reasons must be recorded in `REVIEW.md` under Auto-applied edits or
     Proposed edits.

4. **Owner-facing findings**
   - Pick the findings that the human owner should see in Chinese.
   - Include all HIGH code findings.
   - Include MEDIUM findings if they affect demo, correctness,
     maintainability, or interview/storytelling.
   - Include Tier C doc proposals only if they materially affect the
     user's understanding of what shipped.
   - Exclude bookkeeping noise.

Do not create a separate reconciliation file unless it is useful. The
reconciled decisions must be reflected in `REVIEW.md` and passed to
`demo-narrator`.

---

## Step 3C: Apply approved Tier A/B doc edits yourself

Only the MAIN REVIEW AGENT may modify files.

Read `automation/RUNBOOK.md` section "Doc-update tiers (used by Step 6)"
again before applying edits.

Run the production diff once at the top of this step:

```bash
git -C python-replica diff 6aed9ec6864aebf7cd41a6b3b5859e9ff87dde6d..HEAD --stat -- src/ pyproject.toml
git -C python-replica diff 6aed9ec6864aebf7cd41a6b3b5859e9ff87dde6d..HEAD --name-only -- src/ pyproject.toml
````

Then apply reconciled Tier A/B decisions.

### Tier A — apply automatically only if safe

For each approved Tier A candidate:

1. Locate target file + insertion point.
2. Use Edit to APPEND a row / bullet / section.
3. Do not modify existing content.
4. Do not touch the first 10 lines of README.md.
5. Do not touch the Implementation Roadmap section of CLAUDE.md.
6. Record in `REVIEW.md` later:

```markdown
- Tier A | `<file>` | <one-line summary> | trigger: <RUNBOOK rule> | source: doc-curator candidate / main-agent inspection
```

If unsure whether a candidate is mechanical enough, do NOT apply it.
Downgrade it to Tier C.

### Tier B — create new files if justified

For each approved Tier B candidate:

#### Subsystem doc

1. Copy `automation/templates/subsystem_doc.md` into `docs/<slug>.md`.
2. Fill every `{{placeholder}}` from PLAN.md / HANDOFF.md / diff.
3. If `docs/<slug>.md` already exists, do not overwrite it. Instead,
   append a dated bullet to its `## Recent changes` section if safe;
   otherwise downgrade to Tier C.

#### ADR

1. If `docs/DECISIONS/` does not exist, create it.
2. If `docs/DECISIONS/README.md` does not exist, create it with an index
   table: Number / Date / Title / Status / Initiative.
3. Compute NNNN:

```bash
ls docs/DECISIONS/ | grep -E '^[0-9]{4}' | sort | tail -1 | cut -c1-4
```

Increment by 1 and zero-pad to 4. Start at `0001` if none exists.

4. Slug = kebab-case of the divergence title, <= 6 words.
5. Copy `automation/templates/adr.md` into
   `docs/DECISIONS/<NNNN>-<slug>.md`.
6. Fill every `{{placeholder}}`.
7. Source Context / Decision / Consequences from HANDOFF Section 2 design
   decisions wherever possible.
8. Append a row to `docs/DECISIONS/README.md`.

Record every Tier B creation in `REVIEW.md` later:

```markdown
- Tier B | `<new file path>` | <one-line summary> | trigger: <RUNBOOK rule> | source: doc-curator candidate / main-agent inspection
```

### Tier C — propose only

Do NOT apply Tier C edits. Put them in `REVIEW.md` under:

```markdown
## Proposed edits (need human review)
```

Each entry:

````markdown
1. `<file>:<line-or-section>` — <what to change> — why: <reason>
   Trigger: <RUNBOOK rule>
   Suggested diff:
   ```diff
   - old line
   + new line
````

````

---

## Step 3D: Spawn demo-narrator AFTER reconciliation

Now spawn `demo-narrator`. This is intentionally NOT parallel with
Stage A. The narrator must see the reconciled review findings so the
Chinese owner brief can explain what matters to the user.

Use one `Agent` tool call:

- `subagent_type` = `"general-purpose"`
- `description` = `"owner-brief-narrator-for-auto-memory-overhaul"`
- `prompt` = the literal prompt below PLUS an appended section titled
  `## Additional input from main-agent reconciliation` containing:
  - final code findings to surface to the owner
  - final Tier C proposals to surface to the owner
  - important Tier A/B edits that affect docs the user should know about
  - final pytest/mypy/ruff numbers
  - final commit count and initiative commit range

---

## Subagent 3: `demo-narrator`

`description`: `"owner-brief-narrator-for-auto-memory-overhaul"`

----- BEGIN PROMPT[demo-narrator] -----

You are the **demo-narrator subagent** for the `auto-memory-overhaul`
initiative. Your job is to bridge the cognitive gap between the human
decision-maker, who mainly participated at the initial planning stage,
and the autonomous milestone work that happened afterward.

Your output is in **Chinese (中文)** and becomes the main content of
`OWNER_BRIEF.zh-CN.md`.

You are READ-ONLY. Do not modify any file.

## §Role

Write a Chinese owner-facing walkthrough that answers:

1. **这次交付了什么？** — feature-level, not file-level.
2. **如何演示给别人看？** — concrete commands + expected output.
3. **Before / After 对比？** — baseline behavior vs final behavior.
4. **有哪些项目 owner 必须知道的 finding？** — explain important
   reconciled code/doc findings in Chinese, pruning bookkeeping noise.
5. **如何用于简历 / 面试表达？** — explain the most defensible project
   highlights without exaggeration.

## §Inputs

Read:

1. `python-replica/initiatives/current/PLAN.md`
2. `python-replica/initiatives/current/HANDOFF.md` Section 2
3. `python-replica/initiatives/current/PROGRESS.md`
4. `git -C python-replica log 6aed9ec6864aebf7cd41a6b3b5859e9ff87dde6d..HEAD --oneline`
5. `git -C python-replica diff 6aed9ec6864aebf7cd41a6b3b5859e9ff87dde6d..HEAD -- src/ examples/ README.md tests/`
6. `git -C python-replica show <milestone-commit>` for each milestone,
   especially hunks that reveal user-visible behavior, commands, or demo
   output.
7. The appended section from the MAIN REVIEW AGENT:
   `## Additional input from main-agent reconciliation`.

## §Output schema

Return ONE markdown block in EXACTLY this shape. The main agent will
write it into `OWNER_BRIEF.zh-CN.md`.

```markdown
## 这次交付了什么

按功能列出本次 initiative 交付的具体能力。不要只按文件罗列。每项 1-3 行。
每个交付项必须引用具体 file:line 或 commit SHA。

- **<功能 1 名称>** — <一句话说做了什么>。证据：`<file:line>` 或 commit `<sha>`。
- **<功能 2 名称>** — ...

## 如何演示

给出可以复制到终端运行的演示步骤。命令必须来自实际代码 / examples / tests，不要编造。

### 演示场景 A：<场景标题>

```bash
$ <命令 1>
<期望输出片段，<= 3 行，用 ... 截断长输出>

$ <命令 2>
<期望输出片段>
````

### 演示场景 B：<场景标题，如果有多个独立功能>

```bash
$ <命令>
<期望输出片段>
```

如果某个功能是内部 refactor，没有直接 CLI demo，明确写：
"本功能为内部实现改造，无直接 CLI demo；可通过 `<测试 path>` 或
`<代码 path>` 验证。"

## Before / After 对比

| 项        | 之前（baseline `6aed9ec6864aebf7cd41a6b3b5859e9ff87dde6d`） | 之后（本 initiative 结束） |
| -------- | ---------------------------------- | ------------------- |
| <功能维度 1> | <旧行为>                              | <新行为>               |
| <功能维度 2> | <旧行为>                              | <新行为>               |

至少 2 行。如果功能太内部化，最后一行可以用 pytest count / 测试覆盖增长。

## 用户视角下的关键 finding

只写用户应该知道的实质问题，不重复 scorecard 数字。

* **<finding 标题>** — 严重度 <HIGH/MEDIUM/LOW> — 来源：<code-reviewer finding / doc Tier C proposal / main-agent reconciliation>

  * <中文解释：这是什么问题、为什么影响用户、建议怎么处理>

如果无值得用户特别关注的问题，写：
"(本次未发现需要用户特别关注的问题)"。

## 简历 / 面试可以怎么讲

给出 3-5 条可防守、不过度夸大的表达。每条包括：

* **亮点**：<一句话>

  * **可以怎么说**：<中文表达，必要时附英文关键词>
  * **证据**：`<file:line>` / commit `<sha>` / test command
  * **不要夸大成**：<提醒用户不要怎么说>

## 还需要补什么

列出 1-5 个最值得后续补强的点。按优先级排序。

1. **<补强点>** — <为什么值得补> — <建议下一步>

````

## §Constraints

- 全文用中文；file paths / commit SHAs / CLI flags / code identifiers
  保持英文原样。
- 演示命令必须真实可跑。不要凭想象编造命令。
- 每个交付项必须引用具体 file:line 或 commit SHA。
- 不要写 scorecard。
- 不要提出新的 doc edits。只解释 main-agent reconciliation 传入的 finding。
- 不要修改任何文件。
- 目标是让项目 owner 读完后能快速掌握：做了什么、怎么演示、哪里还不稳、怎么对外讲。

----- END PROMPT[demo-narrator] -----

---

## Step 4: Write `initiatives/current/REVIEW.md`

Use `Write` to create `initiatives/current/REVIEW.md`.

Structure:

```markdown
# REVIEW — auto-memory-overhaul

## Summary

- Initiative period: <start> -> <end>
- Milestones: <count>, all complete
- pytest: <before> -> <after> (delta +N)
- mypy: <status>
- ruff: <status>
- Total commits in this initiative: <N>
- Final pre-wrap commit: `<sha>`
- Review mode: multi-agent staged review (`code-reviewer` + `doc-curator-candidate-finder` in parallel, then reconciled, then `demo-narrator`)

## Lessons learned

- <3-5 bullets — what worked, what to do differently next time>

## Main-agent reconciliation note

Explain briefly:

- whether code-reviewer and doc-curator outputs conflicted
- which findings were deduplicated or severity-adjusted
- which Tier A/B candidates were applied, downgraded, or skipped
- which findings were selected for the owner brief

(paste reconciled code-reviewer's scorecard sections here)

(paste reconciled Detail-level findings here)

## Auto-applied edits

<Tier A/B edits actually applied by the MAIN REVIEW AGENT. If none: write explicit none rows.>

## Proposed edits (need human review)

<Tier C proposals selected by the MAIN REVIEW AGENT. If none: write "(none)">

## Phase 2C: Wrap-up actions taken

<list what you did in Phase 2C, with commands>

## Owner brief

The decision-maker-facing Chinese owner brief lives in
[`OWNER_BRIEF.zh-CN.md`](./OWNER_BRIEF.zh-CN.md). Read that file for
"what was built / how to demo it / before-after / how to talk about it".
````

Rules:

* Do not blindly paste the raw doc-curator candidate list. Record final
  Tier A/B/C decisions only.
* Do not hide unsupported findings. If a subagent finding was rejected,
  mention it briefly in the reconciliation note.
* Keep `REVIEW.md` English.
* Keep `OWNER_BRIEF.zh-CN.md` as the Chinese source for human
  understanding.

---

## Step 5: Write `initiatives/current/OWNER_BRIEF.zh-CN.md`

Use `Write` to create `initiatives/current/OWNER_BRIEF.zh-CN.md`:

```markdown
# OWNER BRIEF（中文）— auto-memory-overhaul

> 本文档给项目 owner 阅读，重点是：这次交付了什么、如何演示、Before/After
> 有什么变化、哪些 finding 需要注意、以及如何把成果用于简历 / 面试表达。
>
> 英文归档审查（含评分卡、Tier A/B/C 决策、wrap-up 记录）见
> [`REVIEW.md`](./REVIEW.md)。

(paste demo-narrator's full reconciled output block here)

## 项目状态一句话

本次 initiative 在 `6aed9ec6864aebf7cd41a6b3b5859e9ff87dde6d..HEAD` 范围共 <N> 个 commit，
最终 pytest <count> 通过（baseline <before>，+<delta>），mypy + ruff
全绿。完整审核结论见 `REVIEW.md`。
```

Do NOT translate the full scorecards into Chinese. Avoid duplication and
future drift. `OWNER_BRIEF.zh-CN.md` is deliberately scoped to user
understanding and demo readiness.

---

# Phase 2C — Wrap-up

Only proceed if:

1. Step 1 passed.
2. Step 2 was green.
3. Stage A subagents returned successfully.
4. Main-agent reconciliation completed.
5. Approved Tier A/B edits, if any, were applied by the main agent.
6. `demo-narrator` returned successfully.
7. `REVIEW.md` and `OWNER_BRIEF.zh-CN.md` were written successfully.

## Step 6: Archive

```bash
cd python-replica
git mv initiatives/current initiatives/_archive/2026-05-auto-memory-overhaul
mkdir initiatives/current
touch initiatives/current/.gitkeep
```

## Step 7: Rewrite `NOW.md`

Use this template. Preserve the prior `## How to start a new initiative`
section verbatim.

```markdown
# NOW — current initiative status

## Active initiative

**None.**

`initiatives/current/` is empty (`.gitkeep` only).

## Last completed initiative

**auto-memory-overhaul** — see
[`initiatives/_archive/2026-05-auto-memory-overhaul/`](./initiatives/_archive/2026-05-auto-memory-overhaul/).

| | |
|---|---|
| Period | <start>-<end> |
| Milestones | M1 -> M{N} |
| Final commit | `<sha>` |
| pytest | <before> -> <after> |
| mypy + ruff | <status> |
| English review | [`REVIEW.md`](./initiatives/_archive/2026-05-auto-memory-overhaul/REVIEW.md) |
| Owner brief 中文 | [`OWNER_BRIEF.zh-CN.md`](./initiatives/_archive/2026-05-auto-memory-overhaul/OWNER_BRIEF.zh-CN.md) |

## How to start a new initiative

<copy verbatim from prior NOW.md>
```

## Step 8: Update `initiatives/README.md`

Move the row for this initiative from the Active table to the Archived
table. Fill:

* final commit
* period
* milestone count
* archive path
* review link
* owner brief link, if the table structure supports it

If the current table has no owner brief column and adding one would be a
subjective schema change, do not rewrite the table. Instead, include the
owner brief path in the archived row's notes/status field if available.
If that is not possible, leave the table structure unchanged and mention
this as a Tier C proposal in `REVIEW.md` if it matters.

## Step 9: Write `review.log`

Write a terse session summary to:

```text
initiatives/_archive/2026-05-auto-memory-overhaul/logs/review.log
```

Use this content shape and fill actual values:

```markdown
Phase 2B + 2C complete (staged multi-agent flow). Summary:

- **All N milestones verified**: `[auto-mem/M1]` (`<sha>`), ...
- **Quality gates green**: pytest <N> (+<delta> from <baseline>), mypy clean (<N files or status>), ruff clean
- **Stage A subagents spawned in parallel**: code-reviewer + doc-curator-candidate-finder
- **Main-agent reconciliation completed**: <N> code findings retained, <N> doc candidates applied/downgraded/skipped
- **Stage B narrator spawned after reconciliation**: demo-narrator
- **REVIEW.md**: scorecards, reconciled detail findings, Tier A/B/C decisions, wrap-up actions
- **OWNER_BRIEF.zh-CN.md**: delivered features, demo commands, Before/After, owner-facing findings, resume/interview talking points
- **Tier A auto-applied**: <one line per edit, or "did not fire: <reason>">
- **Tier B**: <one line per creation, or "did not fire: <reason>">
- **Archive committed** as `<wrap-sha> [auto-mem/wrap]`
- **All wrap-gate checks pass**
- **Main session stayed alive on --remote-control** for user attach.

Key audit findings flagged in REVIEW.md / OWNER_BRIEF.zh-CN.md:
- <up to 3 bullets from retained code findings or Tier C proposals>
```

Then stage it explicitly:

```bash
git add initiatives/_archive/2026-05-auto-memory-overhaul/logs/review.log
```

## Step 10: Commit

Stage every path Phase 2C wrap + Step 3C Tier A/B edits may have touched.
Use explicit paths. Project convention: no `git add -A`.

```bash
cd python-replica

git add initiatives/                  # archived initiative + new current/.gitkeep + index + REVIEW.md + OWNER_BRIEF.zh-CN.md
git add NOW.md                        # rewritten by Step 7
git add CLAUDE.md README.md           # Tier A may have appended; no-op if untouched
git add docs/                         # Tier B may have created subsystem docs / ADRs / DECISIONS dir

git commit -m "[auto-mem/wrap] post-execution review + archive (multi-agent)

REVIEW.md          : initiatives/_archive/2026-05-auto-memory-overhaul/REVIEW.md
OWNER_BRIEF.zh-CN  : initiatives/_archive/2026-05-auto-memory-overhaul/OWNER_BRIEF.zh-CN.md
Final pytest       : <count>. mypy + ruff clean.
Review flow        : code-reviewer + doc-curator-candidate-finder, reconciled by main agent, then demo-narrator.
"
```

After commit, verify the working tree is clean:

```bash
if [ -n "$(git status --short)" ]; then
  echo "ERROR: working tree dirty after wrap commit:"
  git status --short
  echo "Some Tier A/B edits were not staged. Add them and amend, or"
  echo "investigate which Step 3C action produced unstaged changes."
  exit 1
fi
```

## Step 11: Stay alive on `--remote-control`

After the wrap-gate verifies, print **exactly** this line to stdout:

```text
Review complete. OWNER_BRIEF.zh-CN.md is at initiatives/_archive/2026-05-auto-memory-overhaul/OWNER_BRIEF.zh-CN.md. Attach to this session via your browser extension or Claude desktop app to ask follow-up questions in any language, or /exit to end this session.
```

Then **wait**.

Do **NOT** call `/exit`.
Do **NOT** print a final summary that signals the task is finished.
Do **NOT** call any tool whose only purpose is to end the session.
The session must stay on `--remote-control` until the user types `/exit`.

When the user attaches and asks a question:

* Use read-only tools such as Read, Grep, Bash, git diff, and git show to
  gather evidence.
* Answer in the language the user uses. Chinese is the default for this
  initiative because the owner brief is Chinese.
* Cite files, commits, and commands wherever useful.
* After answering, wait again. Do not volunteer unnecessary next steps.

When the user types `/exit`, the session terminates and the shell
script's outer `if ! claude --remote-control ... ; then die ...; fi`
continues. The wrap-gate has already been verified by Step 6-10, so the
script should record a successful exit.
