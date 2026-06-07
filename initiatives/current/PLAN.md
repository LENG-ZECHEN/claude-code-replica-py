---
slug: plan-surface
commit_prefix: plan-srf

milestones:
  M1:
    name: TodoWrite (V1) tool + teaching prompt + turn-based reminder
    phase_ids: [T1, T2, T3]
    exit_gate: |
      tests/test_todo.py and tests/test_repl_todo.py pass; pytest total
      grows by ≥ 14. ToolRegistry exposes `todo_write` (NOT deferred —
      directly in the initial schema). A MockProvider script invoking
      todo_write produces correct `_todos` mutation observable via REPL
      `/todos` with glyphs. A second MockProvider script running ≥ 10
      assistant turns WITHOUT calling todo_write causes EXACTLY ONE
      `ATTACHMENT_TODO_NUDGE` USER message to appear in
      `BuiltContext.api_messages` at turn 10; the content includes the
      verbatim V1 reminder text fragment `"hasn't been used recently"`
      AND the current todo list echo when non-empty; turns 11-19 do NOT
      re-inject (cooldown); turn 20 re-injects (cycle resumes). Both
      `--todo-reminder-turns 3` and `--no-todo-reminder` flags work as
      documented in `simple-agent --help`. With todo_write NOT registered,
      the nudge machinery is fully quiescent (no trace emits, no metric
      bumps, no attachments) even after 30 assistant turns.
    notes: |
      Source mapping (read these BEFORE implementing — every claim below
      ties to a specific line range):
        - claude-code-source-code/src/tools/TodoWriteTool/TodoWriteTool.ts (115 lines)
        - claude-code-source-code/src/tools/TodoWriteTool/prompt.ts (~185 lines, the teaching PROMPT)
        - claude-code-source-code/src/utils/todo/types.ts (19 lines, schema)
        - claude-code-source-code/src/utils/tasks.ts:133-139 (isTodoV2Enabled — explains why V1 is the right pick for our scope)
        - claude-code-source-code/src/utils/attachments.ts:254-256 (TODO_REMINDER_CONFIG constants)
        - claude-code-source-code/src/utils/attachments.ts:3212-3317 (turn counter + injection gate)
        - claude-code-source-code/src/utils/messages.ts:3663-3678 (todo_reminder → user message rendering)

      Scope: replicate V1 (the single-tool TodoWrite form) — NOT V2 (the
      6-tool Tasks suite). In TS the two are mutually exclusive: V1's
      `isEnabled = !isTodoV2Enabled()` (TodoWriteTool.ts:53), V2's
      `isEnabled = isTodoV2Enabled()` (TaskCreateTool.ts:69 and 5 siblings).
      V1 is single-tool, in-memory, no persistence, no DAG, no swarm —
      exactly what our single-process replica needs and matches the
      immutable-transcript style already established in M1-M7.

      Explicitly NOT implemented from V1/V2 (record in Current Limitations
      AND as in-file comments at the cited TS line ranges):
        - V2 Tasks suite — 6 tools, file persistence (.tasks/<id>.json
          + .highwatermark), lockfile-protected concurrency, swarm-shared
          task list, blocks/blockedBy DAG, owner field. Out-of-scope.
        - `shouldDefer: true` (TodoWriteTool.ts:51) — replica has no
          ToolSearch tool, so deferred lazy-load degrades to "directly load
          into schema". Document in todo_tool.py header.
        - BRIEF mutex short-circuit (attachments.ts:3284-3289) — no Brief
          tool here.
        - Global `CLAUDE_CODE_DISABLE_ATTACHMENTS` env switch
          (attachments.ts:752-761) — replica uses per-mechanism enable
          flags (matches auto_memory_enabled / extract_memories_enabled).
        - `verificationNudgeNeeded` branch (TodoWriteTool.ts:76-86) —
          growthbook-flagged in TS; no verification agent in this replica.
        - Per-(agentId | sessionId) todo namespacing (TodoWriteTool.ts:67)
          — single-agent replica, _todos is one instance field.

      ─── V1 has three required pieces; complete replica = all three ───

      ① TOOL BODY (mirrors TodoWriteTool.ts lines 65-103)

      New file: src/simple_coding_agent/todo.py
        - `TodoStatus` StrEnum: PENDING / IN_PROGRESS / COMPLETED
        - `TodoItem` frozen dataclass: `content: str` (≥1 char), `status:
          TodoStatus`, `activeForm: str` (≥1 char)
        - `TodoNudge` frozen dataclass mirroring `SnipNudge` shape:
          `todos: tuple[TodoItem, ...]`
        - Pure `render_todo_nudge_body(todos: tuple[TodoItem, ...]) -> str`
          producing the EXACT V1 reminder text from messages.ts:3668 followed
          by the optional list-echo block from messages.ts:3669-3671:
          `"Here are the existing contents of your todo list:\n\n[1. [pending] X\n2. [in_progress] Y]"`.
          When `todos` is empty, only the reminder text (no echo block) —
          confirms with user decision: "严格照 V1（空也 nag）".
        - Pure `count_assistant_turns_since(messages, predicate) -> int`:
          - Iterate `reversed(messages)`
          - Count only `msg.role == ASSISTANT`
          - Skip thinking messages (replica has no thinking role today; keep
            the rule for source fidelity and forward-compat — cheap guard)
          - Stop accumulation when `predicate(msg)` returns True
          - The matching message itself does NOT count as "1 turn since"
            (check predicate BEFORE the ++; see TS comment at
            attachments.ts:3232-3233)

      New file: src/simple_coding_agent/todo_tool.py
        - `register_todo_write_tool(registry, get_todos, set_todos)` factory.
        - Tool fn validates JSON schema strictly (strictObject), then:
            allDone = all(t.status == COMPLETED for t in parsed)
            set_todos([] if allDone else parsed)   # TS line 70 equivalent
        - Returns EXACTLY the TS string (TodoWriteTool.ts lines 104-114):
          "Todos have been modified successfully. Ensure that you continue
           to use the todo list to track your progress. Please proceed with
           the current tasks if applicable"
        - JSON schema:
          { todos: array of { content: str≥1, status: enum[pending,in_progress,completed], activeForm: str≥1 } }

      ② TEACHING PROMPT (mirrors TodoWriteTool.ts `prompt()` lines 39-41)

      The ~185-line PROMPT in prompt.ts is the "when to call TodoWrite"
      driver. Without it the tool is dead weight — the model has the
      schema but no signal to use it proactively.

      Approach: append the TS PROMPT VERBATIM as a static
      `## Todo Management` section to the base system prompt, gated by an
      `enable_todo_teaching: bool = True` AgentLoop kwarg. Static text →
      cache-prefix-stable, same pattern auto-memory M3 used for
      `## Memory Management`. Splice order in the system prompt:
        base prompt → ## Memory Management → ## Todo Management
      (Plan Mode block lands in M2 after this section.)

      ③ TURN-BASED REMINDER (mirrors attachments.ts:3212-3317 + messages.ts:3663-3678)

      Constants & CLI flags:
        - `TODO_REMINDER_TURNS: int = 10` — SINGLE constant covering both
          AND branches (per user decision: collapse TS's separate
          TURNS_SINCE_WRITE + TURNS_BETWEEN_REMINDERS into one because
          both are 10 by default; explicit trade-off note in todo.py
          header that this couples the "detection" and "cooldown"
          semantics into one knob).
        - `--todo-reminder-turns <int>` CLI flag (both cli.py and openai_cli.py).
        - `--no-todo-reminder` CLI flag flips `todo_nudge_enabled` to False.
        - `AgentLoop(..., todo_nudge_enabled: bool = True, todo_reminder_turns: int = 10)`.

      Short-circuits (ONLY two — every other TS short-circuit is omitted
      or naturally absorbed by the counter logic):
        - `todo_nudge_enabled is False` → entire machinery skipped.
        - `"todo_write" not in tool_registry._tools` → ditto. CHECK ONCE at
          AgentLoop `__post_init__`, store as
          `_todo_nudge_machinery_enabled: bool` (`init=False`); do NOT
          re-check every turn.
        - TS short-circuit (c) "messages empty" → absorbed naturally:
          `count_assistant_turns_since` on an empty transcript returns 0,
          never hits threshold. No explicit check.
        - BRIEF mutex / global DISABLE_ATTACHMENTS → explicitly NOT done.

      Arm logic (in AgentLoop, per user turn, AFTER appending the new
      user input message but BEFORE Provider.call() / stream_call()):
        if not self._todo_nudge_machinery_enabled:
            return
        n = self._todo_reminder_turns
        since_write = count_assistant_turns_since(
            transcript, _is_todo_write_call)
        since_reminder = count_assistant_turns_since(
            transcript, _is_todo_reminder_attachment)
        if since_write >= n and since_reminder >= n:   # ← strict V1 double-AND
            self._todo_nudge = TodoNudge(todos=tuple(self._todos))
        else:
            self._todo_nudge = None
      The AND is the V1 contract — `since_write` decides "should we remind",
      `since_reminder` enforces "don't spam every turn while ignored". One
      condition only → noise floor. Both → spec-faithful. (Mirrors
      `SnipNudge` arm/clear pattern already in the codebase.)

      Predicates (in todo.py, also pure functions):
        - `_is_todo_write_call(msg)`: ASSISTANT msg with any ToolCall
          where `name == "todo_write"`.
        - `_is_todo_reminder_attachment(msg)`: msg.type == ATTACHMENT_TODO_NUDGE.

      Injection (ContextBuilder.build() gains kwarg `todo_nudge: TodoNudge | None = None`):
        - When set, prepend ONE USER-role message with content
          `<system-reminder>\n{render_todo_nudge_body(nudge.todos)}\n</system-reminder>`
          typed as `MessageType.ATTACHMENT_TODO_NUDGE` so the next turn's
          counter can identify it via the enum.
        - Front-to-back ordering when multiple attachments arm in one turn:
          `[file_snapshots, snip_nudge, todo_nudge, ...kept_messages]`.
          `_coalesce_same_role` already handles user-role merging.
        - AgentLoop clears `self._todo_nudge` after the build/call cycle
          (one-shot, same as SnipNudge).

      Modified files:
        - models.py — add `MessageType.ATTACHMENT_TODO_NUDGE`; classmethod
          `Message.attachment_todo_nudge(content: str) -> Message` mirroring
          `attachment_memory()`.
        - transcript.py — grep for `ATTACHMENT_MEMORY` enumerations
          (filtering paths) and add the sibling `ATTACHMENT_TODO_NUDGE`
          at every match.
        - compact.py — same pattern: `if msg.type in (COMPACT_BOUNDARY,
          ATTACHMENT, ATTACHMENT_MEMORY, ATTACHMENT_TODO_NUDGE): ...`.
        - context.py — new `todo_nudge` kwarg on `build()`; prepend logic
          per above; splice the static `## Todo Management` teaching block
          into the system prompt after `## Memory Management`.
        - loop.py —
            `_todos: list[TodoItem] = field(default_factory=list)`
            `_todo_nudge: TodoNudge | None = None`
            `_todo_nudge_machinery_enabled: bool = field(init=False)`
            `__post_init__`: compute `_todo_nudge_machinery_enabled =
              todo_nudge_enabled and "todo_write" in self._tool_registry._tools`
            Conditionally call `register_todo_write_tool(self._tool_registry,
              lambda: list(self._todos),
              lambda v: setattr(self, "_todos", list(v)))` when enabled.
            Arm before each Provider.call() / stream_call(); clear after.
        - tool_registry_factory.py — register `todo_write` for both
          MockProvider and OpenAIProvider tool sets (no defer — directly
          in the initial tools list).
        - cli.py — `/todos` slash command prints the list with glyphs
          (☐ pending, ▶ in_progress, ☑ completed); `/help` lists it.
          Add `--todo-reminder-turns <int>` and `--no-todo-reminder` flags.
          openai_cli.py inherits through `_drive_repl_session`.
        - trace.py — register a 10th channel `todo`. Emit per call:
          `todo channel=todo action=write count=N completed=K` after a
          todo_write tool call; `todo channel=todo nudge_armed=1 pending=N
          since_write=W since_reminder=R` when the AND is satisfied.
          Update CLAUDE.md trace.py per-file summary in the exit ritual
          to note vocabulary growth 9 → 10.
        - metrics.py — `todo_writes: int = 0`, `todo_nudges_armed: int = 0`.

      Testing (≥ 14 cases across the two files):
        - tests/test_todo.py
          - schema validation: missing content / empty content / bad enum /
            missing activeForm / numeric content rejected (5 cases)
          - allDone collapse: 3 items all completed → state becomes [] (1)
          - allDone partial: 2 completed + 1 pending → state holds all 3 (1)
          - render_todo_nudge_body: empty todos → reminder text only,
            no echo block (1); populated todos →
            "[1. [pending] X\n2. [in_progress] Y]" exact echo (1)
          - count_assistant_turns_since: 0 on empty (1); counts only
            assistant (1); skips thinking when introduced (xfail/skip
            placeholder, 1); stops at first predicate hit (1);
            "matching message itself doesn't count" invariant (1)
        - tests/test_repl_todo.py
          - `/todos` shows "no todos" on a fresh AgentLoop (1)
          - After MockProvider scripts a todo_write call: `/todos` prints
            list with correct glyphs (1)
          - **CORE 10-turn cycle test**: MockProvider script that never
            calls todo_write — turn 10 BuiltContext.api_messages includes
            ATTACHMENT_TODO_NUDGE USER message whose content contains
            "hasn't been used recently"; turns 11-19 do NOT re-include it;
            turn 20 re-injects (1)
          - `--todo-reminder-turns 3` collapses cycle to 3 (1)
          - `--no-todo-reminder`: no attachment even after 30 turns (1)
          - todo_write NOT registered (build a loop without the tool):
            machinery quiescent, no trace emit, no metric bump (1)
        - tests/test_trace.py — new `todo` channel format + no-raw-content
          invariant (extend existing negative-cases pattern).

  M2:
    name: PermissionMode + Tool.read_only flag + plan_mode attachment + EnterPlanMode tool + ToolExecutor soft-deny
    phase_ids: [P1, P2, P3]
    exit_gate: |
      tests/test_permission_mode.py, tests/test_enter_plan_mode.py, and
      tests/test_plan_mode_soft_deny.py pass; pytest total grows by ≥ 14.
      AgentLoop carries `_permission_mode: PermissionMode = NORMAL`.
      ToolRegistry exposes `enter_plan_mode` (NOT deferred, directly in
      the initial schema). A MockProvider script that calls
      enter_plan_mode then attempts write_file produces:
      (a) `_permission_mode == PLAN` after turn 1;
      (b) the API `tools` field passed into Provider.call() on turn 2 is
          BYTE-IDENTICAL to turn 1 (verified by deep-equal assert — proves
          schema is mode-invariant and prompt cache prefix is preserved);
      (c) turn 2's BuiltContext.api_messages contains a USER-role
          `<system-reminder>` ATTACHMENT_PLAN_MODE block (verbatim text
          fragment "DO NOT write or edit any files yet");
      (d) write_file ToolCall in turn 2 produces a ToolResult with
          `is_error=True` and content includes "Plan mode active:
          'write_file' is not allowed";
      (e) read_file in plan mode executes normally (is_error=False).
    notes: |
      Source mapping (read these BEFORE implementing — confirm what TS
      does NOT do, not just what it does):
        - claude-code-source-code/src/tools/EnterPlanModeTool/EnterPlanModeTool.ts (126 lines)
        - claude-code-source-code/src/tools/EnterPlanModeTool/prompt.ts (~170 lines, only the "external" variant — skip USER_TYPE=ant branch)
        - claude-code-source-code/src/tools.ts:271-327 (getTools — CRITICAL: this function does NOT filter by mode. The tools field is mode-invariant.)
        - claude-code-source-code/src/utils/attachments.ts:881 (`maybe('plan_mode', ...)` per-turn dispatch)
        - claude-code-source-code/src/utils/attachments.ts:1186 (getPlanModeAttachments — gated by mode === 'plan')
        - claude-code-source-code/src/utils/messages.ts:3826 (case 'plan_mode' → getPlanModeInstructions → system-reminder USER message)
        - claude-code-source-code/src/utils/permissions/permissions.ts:932 (`shouldAvoidPermissionPrompts` headless → auto-deny — the ask→deny degradation we mirror in non-interactive mode)
        - claude-code-source-code/src/utils/planModeV2.ts (95 lines) — read for context only; growthbook gates, interview-phase, pewter-ledger experiment all OUT OF SCOPE.

      Critical architecture decision (informs every step below):
      ──────────────────────────────────────────────────────────
      TS's plan mode does NOT filter tools at the schema layer. The API
      `tools` field is identical in NORMAL and PLAN mode. Constraint is
      enforced via TWO mechanisms:
        (1) per-turn `<system-reminder>` attachment teaching the model to
            self-restrict (the load-bearing mechanism — ~95% of the
            policing happens here);
        (2) runtime ask/deny at the permission layer when the model
            doesn't self-restrict (headless degrades to deny).
      We mirror this exactly: the `tools` JSON stays mode-invariant
      (preserves prompt cache prefix), attachment is the main lever,
      ToolExecutor soft-deny is the safety net.

      New files:
        - src/simple_coding_agent/permission.py
          - `class PermissionMode(StrEnum): NORMAL = "normal"; PLAN = "plan"`
          - `ENTER_PLAN_MODE_TEACHING_TEXT: str` — verbatim copy of the
            6-step "In plan mode, you should..." block from
            EnterPlanModeTool.ts:108-118, used both as the EnterPlanMode
            tool_result string AND as the per-turn attachment body.
            Single source of truth. (Replace AskUserQuestion with comment
            "no direct equivalent in this replica" but keep the line so
            the model's instructions stay faithful to TS.)
          - `PlanModeAttachment` frozen dataclass mirroring SnipNudge:
            opaque marker the ContextBuilder consumes; carries no state
            beyond the teaching text constant.
          - NOTE: no `filter_tools_for_mode`, no `READ_ONLY_TOOLS` set.
            Tool/Mode coupling is moved to Tool.read_only flag (see below).

        - src/simple_coding_agent/plan_mode_tools.py
          - `register_enter_plan_mode_tool(registry, mode_setter)` factory
            mirroring snip_tool_model.register_snip_history_tool shape.
            Tool fn signature: `() -> str`. Body:
              `mode_setter(PermissionMode.PLAN)`
              `return ENTER_PLAN_MODE_TEACHING_TEXT`
            EnterPlanMode tool itself is `read_only=True` (model can call
            it from inside plan mode — it's idempotent — and from normal
            mode to enter).

      Modified files:
        - tools.py — Tool dataclass gains `read_only: bool = False` field
          alongside the existing `max_result_chars: int | None = MAX_RESULT_CHARS`.
          Every existing tool registration audited and tagged:
            read_only=True: read_file, list_files, search_text, snip_history,
                            todo_write (M1), enter_plan_mode (M2),
                            exit_plan_mode (M3 will register)
            read_only=False (default, no change needed): write_file, run_shell,
                            write_memory_entry
          The `ToolRegistry.to_api_schema()` signature is UNCHANGED — no
          permission_mode param. Mode-based filtering is NOT done here.
        - loop.py
          - `_permission_mode: PermissionMode = PermissionMode.NORMAL`
            instance field.
          - `_set_permission_mode(mode)` helper. Emits `permission` trace
            channel + records `plan_mode_entries` / `plan_mode_exits` metric.
            Passed into EnterPlanMode factory's mode_setter closure.
          - **`_execute_one` soft-deny hook**: insert BEFORE the existing
            try/except (loop.py:766-797 — the function already does hooks
            for read_file file-snapshot capture, so this fits the
            established pattern):
              if (self._permission_mode == PermissionMode.PLAN
                      and not self._registry.get(call.name).read_only):
                  return ToolResult(
                      tool_use_id=call.id,
                      content=(f"Plan mode active: '{call.name}' is not "
                               f"allowed. Use ExitPlanMode to submit your "
                               f"plan for approval, or use /plan to exit "
                               f"plan mode manually."),
                      is_error=True,
                  )
            ToolExecutor itself UNCHANGED. Policy lives in AgentLoop
            (loop-level concern); mechanism stays in ToolExecutor
            (executes registered tools). Single-responsibility preserved.
          - `_maybe_arm_plan_mode_attachment()` per-turn helper: when
            `_permission_mode == PLAN`, set `self._plan_mode_attachment
            = PlanModeAttachment()`; else None. Called immediately after
            the user input is appended, before `ContextBuilder.build()`.
            Same arm/clear pattern as SnipNudge (one-shot per turn).
        - context.py
          - `build()` gains kwarg `plan_mode_attachment: PlanModeAttachment | None = None`.
          - When set, prepend ONE USER-role dict containing
            `<system-reminder>\n{ENTER_PLAN_MODE_TEACHING_TEXT}\n</system-reminder>`
            typed as `MessageType.ATTACHMENT_PLAN_MODE`.
          - Final front-to-back order after all attachments arm:
            `[file_snapshots, snip_nudge, todo_nudge (M1),
              plan_mode_attachment (M2), ...kept_messages]`
          - `_coalesce_same_role` already handles user-role merging.
          - `_plan_mode_dict(attachment)` helper mirroring existing
            `_snip_nudge_dict()` at context.py:240 — ~6 lines.
          - System prompt is NOT modified per turn (the static text in
            the base prompt does not change with mode). The attachment
            IS the per-turn signal. Rationale: keeps prompt-cache prefix
            stable across the system block.
        - models.py — add `MessageType.ATTACHMENT_PLAN_MODE = "attachment_plan_mode"`;
          classmethod `Message.attachment_plan_mode(content: str) -> Message`
          mirroring `attachment_memory()`.
        - transcript.py / compact.py — grep for `ATTACHMENT_MEMORY` in
          enumeration lists and add the new value (same pattern M1 does
          for ATTACHMENT_TODO_NUDGE).
        - tool_registry_factory.py — register `enter_plan_mode` for both
          MockProvider and OpenAIProvider tool sets.
        - trace.py — register a `permission` channel (now grows 9 → 10
          [todo from M1] → 11 [permission from M2]). Emit
          `permission channel=permission mode=plan source=enter_plan_mode_tool`
          on transition; `permission channel=permission mode=plan source=slash`
          for the `/plan` REPL entry (M3 lands the slash; emit site is
          shared).
        - metrics.py — `plan_mode_entries: int = 0`,
          `plan_mode_exits: int = 0`, `plan_mode_write_attempts: int = 0`
          (bumped by the soft-deny branch).

      Explicitly NOT implemented (record in Current Limitations):
        - `getTools(toolPermissionContext)` mode filtering at TS
          tools.ts:271-327 — TS doesn't filter either; the function
          accepts a permissionContext only for deny-rule processing.
          The replica's `ToolRegistry.to_api_schema()` keeps its
          mode-invariant signature.
        - TS's two-stage permission pipeline (ask→user-confirmation→deny)
          — replica goes straight to deny via ToolExecutor soft-deny since
          there's no UI gate to "ask" through.
        - Plan file persistence (deferred to never; M3 explicit out).
        - `prePlanMode` stashing (TS preserves the mode you were in
          before plan to restore on exit) — replica has only NORMAL/PLAN,
          implicit restoration is fine.

      Testing (≥ 14 cases):
        - tests/test_permission_mode.py
          - PermissionMode enum values + str representation (1)
          - PlanModeAttachment frozen / immutable / hash-stable (1)
          - ENTER_PLAN_MODE_TEACHING_TEXT contains "DO NOT write or edit
            any files yet" verbatim (1)
        - tests/test_enter_plan_mode.py
          - register_enter_plan_mode_tool produces a Tool with
            read_only=True (1)
          - Tool fn invocation flips mode via mode_setter (1)
          - Tool fn returns the exact ENTER_PLAN_MODE_TEACHING_TEXT (1)
          - MockProvider integration: turn 1 model calls enter_plan_mode →
            AgentLoop._permission_mode becomes PLAN (1)
          - **API schema invariance**: capture `tools` JSON passed to
            Provider.call() at turn 1 (NORMAL) and turn 2 (PLAN); assert
            deep-equal — proves cache prefix preserved (1)
          - turn 2 BuiltContext.api_messages includes ATTACHMENT_PLAN_MODE
            USER message with the teaching text (1)
        - tests/test_plan_mode_soft_deny.py
          - write_file ToolCall in plan mode → ToolResult is_error=True,
            content matches "Plan mode active: 'write_file' is not allowed" (1)
          - run_shell ToolCall in plan mode → same (1)
          - write_memory_entry ToolCall in plan mode → same (1)
          - read_file ToolCall in plan mode → executes normally,
            is_error=False (1)
          - todo_write ToolCall in plan mode → executes normally (1)
          - plan_mode_write_attempts metric bumps once per soft-deny (1)

      Out of scope for M2 (deferred to M3):
        - ExitPlanMode tool registration + CLI approval flow.
        - `/plan` slash command surface + REPL UX prints.
        - openai_cli surface wiring (M3 inherits via _drive_repl_session).

  M3:
    name: ExitPlanMode tool + CLI approval + bidirectional /plan toggle
    phase_ids: [P4, P5]
    exit_gate: |
      tests/test_exit_plan_mode.py and tests/test_repl_plan_mode.py
      pass; pytest total grows by ≥ 10. REPL `/plan` slash command is a
      BIDIRECTIONAL toggle: NORMAL → PLAN prints `"Plan mode entered.
      Write tools will be soft-rejected. Use /plan again to exit, or let
      the model call ExitPlanMode."`; PLAN → NORMAL prints `"Plan mode
      exited. Write tools re-enabled."`. Both transitions are silent
      (no approval prompt); both emit a `permission` trace with
      `source=slash`. When the model calls `exit_plan_mode` with a
      `plan: str` arg, the CLI blocks on
      `input("Approve plan? (y/N): ")`:
        - "y" / "Y" → mode flips to NORMAL, tool_result content is
          "Plan approved. Exiting plan mode.";
        - "n" / "N" / "" / EOF / KeyboardInterrupt → mode stays PLAN,
          PlanRejectedError raised → ToolExecutor sets is_error=True,
          content is "Plan rejected by user. Stay in plan mode and refine."
      openai_cli REPL inherits identical behaviour via
      `_drive_repl_session`. Critical invariant: across the entire
      plan-mode lifecycle, transcript history is preserved across
      transitions (so the model can continue with the read_file /
      search_text context it accumulated during planning, after the
      user uses `/plan` to exit).
    notes: |
      Source mapping:
        - claude-code-source-code/src/tools/ExitPlanModeTool/ExitPlanModeV2Tool.ts (493 lines)
          Read ONLY the core call() path and the approval-rejected branch.
          The 493 lines include feature flags, teammate mailbox, plan-file
          persistence, autoMode integration, analytics, reentry
          attachments, allowedPrompts schema — ALL out of scope.

      Design decisions confirmed with owner (record in code comments):
        - `/plan` is a SYMMETRIC TOGGLE (NORMAL ↔ PLAN) without approval
          prompt. Rationale: the user needs a fast manual escape that
          preserves the transcript context (the read_file / search_text /
          todo_write history accumulated during planning) so they can
          continue work in NORMAL with the plan-mode context inherited.
          This differs from the strict "ExitPlanMode is the only legal
          way out" stance — but matches the source's spirit (the TS
          `/plan` slash is also bidirectional via the underlying
          `setMode` API).
        - EnterPlanMode tool calls do NOT prompt for user approval —
          entering plan mode is the safer direction (tightens
          constraints), so no gate is needed.
        - ExitPlanMode tool calls DO prompt for user approval — model
          is asking for write privileges back, that's the gated step.
        - REPL prints a one-line visual confirmation on every mode
          transition (`/plan` and ExitPlanMode both). Keeps the user
          in the loop without requiring UI animations.

      New files: none. `plan_mode_tools.py` (created in M2) gains a
      second factory.

      Modified files:
        - plan_mode_tools.py
          - `class PlanRejectedError(RuntimeError)` — mirrors
            `SnipRefusedError` in snip_tool_model.py (typed exception
            so ToolExecutor sets is_error=True at loop.py:766-797).
          - `register_exit_plan_mode_tool(registry, mode_setter,
            approval_callback)` factory. The Tool spec:
              name = "exit_plan_mode"
              read_only = True  # the tool itself is read-only; the side effect is mode flip
              input_schema = strictObject({ plan: string≥1 })
              fn:
                  if approval_callback(plan):
                      mode_setter(PermissionMode.NORMAL)
                      return "Plan approved. Exiting plan mode."
                  raise PlanRejectedError(
                      "Plan rejected by user. Stay in plan mode and refine.")
        - cli.py
          - `_handle_slash_command` gains a `/plan` case that toggles:
              if loop is None:
                  print("Cannot toggle plan mode outside a loop.")
                  return ""
              if loop._permission_mode == PermissionMode.NORMAL:
                  loop._set_permission_mode(PermissionMode.PLAN)
                  print("Plan mode entered. Write tools will be "
                        "soft-rejected. Use /plan again to exit, or "
                        "let the model call ExitPlanMode.")
              else:
                  loop._set_permission_mode(PermissionMode.NORMAL)
                  print("Plan mode exited. Write tools re-enabled.")
              return ""
            (The `_set_permission_mode` trace site already passes
            `source="slash"` vs `source="enter_plan_mode_tool"` —
            wired in M2.)
          - `_confirm_exit_plan(plan_text: str) -> bool` helper:
              print("\n--- Proposed plan ---")
              print(plan_text)
              print("---------------------")
              try:
                  return input("Approve plan? (y/N): ").strip().lower() == "y"
              except (EOFError, KeyboardInterrupt):
                  return False
            Located near `_handle_slash_command` for proximity.
          - `_build_repl_loop()` passes `_confirm_exit_plan` as
            approval_callback when invoking
            `register_exit_plan_mode_tool`.
          - `/help` text gains:
              "  /plan                          Toggle plan mode "
              "(silently; bidirectional). Writes are soft-rejected "
              "while in plan mode.\n"
        - openai_cli.py — no per-file change. Inherits the slash
          command + approval prompt via `_drive_repl_session`
          (validated as part of M5 of RUNTIME_ACTIVATION_PLAN — this
          IS the payoff of that earlier extraction).
        - tool_registry_factory.py — register `exit_plan_mode` for
          both MockProvider and OpenAIProvider tool sets.
        - metrics.py — counters added in M2 grow here:
          `plan_mode_exits_approved`, `plan_mode_exits_rejected`. The
          M2 generic `plan_mode_exits` is the SUM (computed as
          approved+rejected, not stored separately).

      Explicitly out of scope (record in CLAUDE.md Current Limitations):
        - Plan-content file persistence (TS plans.ts writeFile +
          getPlanFilePath).
        - allowedPrompts schema (TS scoped-Bash permission requests in
          ExitPlanMode).
        - Reentry attachment (TS plan_mode_reentry message kind sent
          after rejection to remind the model how to refine).
        - Analytics + teammate mailbox + autoMode integration.

      Testing (≥ 10 cases):
        - tests/test_exit_plan_mode.py
          - register_exit_plan_mode_tool produces a Tool with
            read_only=True (1)
          - schema validation: missing plan / empty plan / non-string
            plan rejected (3)
          - approval_callback returns True → mode_setter called with
            NORMAL, fn returns approval text (1)
          - approval_callback returns False → PlanRejectedError raised
            with the rejection text (1)
          - End-to-end through ToolExecutor: approve → ToolResult
            is_error=False; reject → ToolResult is_error=True with
            rejection text (1)
        - tests/test_repl_plan_mode.py
          - `/plan` from NORMAL: mode → PLAN, prints "Plan mode entered"
            line, emits trace source=slash (1)
          - `/plan` from PLAN (toggle back): mode → NORMAL, prints
            "Plan mode exited" line, emits trace source=slash, and
            transcript history is preserved (assert that pre-toggle
            messages still in `loop._transcript.all_messages()`) (1)
          - `/help` lists `/plan` with the toggle description (1)
          - **Full E2E with model**: MockProvider script enters plan
            mode via tool; model calls exit_plan_mode; monkeypatched
            `input()` returns "y" → REPL prints approval message and
            `_permission_mode` reverts to NORMAL; same script with
            monkeypatched `input()` returning "n" → REPL prints
            rejection text and `_permission_mode` stays PLAN (1)
          - openai_cli REPL: same /plan toggle behaviour (smoke test
            via _drive_repl_session integration) (1)
---

> Bootstrapped on 2026-06-08. Baseline commit: `17e616d`. Baseline pytest: 835 passing.
> SIZING WAIVED: M1 and M2 each touch 11 src files but ~5 are 1-3 line trivial diffs (enum/counter/branch additions). Implementation LOC ~80-110 per milestone, well below the obs-thresholds M1 thrash precedent (which had a new Protocol penetrating the tree). Per-pattern precedent: auto-memory M3 + SnipNudge succeeded with similar 5-file fanout.

# Goal

Activate Claude Code's two flagship "planning surface" mechanisms in the
Python replica: the **TodoWrite** tool (a declarative session task list
with an auto-injected stale-todo nudge) and **Plan Mode** (a permission
mode that filters the model-facing tool schema to a read-only whitelist
plus EnterPlanMode/ExitPlanMode tools with a CLI approval gate).
Together they make the replica's "plan" surface match the source
behaviorally: the model can express intent declaratively (todos), be
constrained structurally (plan-mode whitelist), and re-enter normal mode
only after explicit user approval.

# Background / motivation

After M5 of RUNTIME_ACTIVATION_PLAN the replica had reached parity on
context (compact/snip/microcompact), memory (project + extraction +
recall), and the live observable trace surface. The remaining
high-value mechanism in CC v2.1.88 that the replica does NOT model is
the planning surface — exactly the layer that gives Claude Code its
"agentic" feel from a user POV. Two concrete drivers:

1. **TodoWrite** is the smallest, most demonstrable example of
   declarative state held BY the model THROUGH tool calls. The state
   machine is trivial (3 statuses + an allDone-collapse) but the
   `<system-reminder>` nudge that fires when todos drift unblocks a
   broader story: it lets us reuse the existing SnipNudge /
   inject_memory_attachments attachment-injection path for a THIRD
   nudge type, proving the path is a general abstraction not three
   one-offs.

2. **Plan Mode** is a clean instance of "constrain the model with
   prompts + a safety net, NOT by mutating the tool schema". The TS
   source — counter to naïve intuition — does NOT filter tools at the
   schema layer ([tools.ts:271-327](claude-code-source-code/src/tools.ts:271)
   `getTools` accepts a permissionContext only for deny-rule processing,
   no mode filter). Instead two mechanisms cooperate:
   (a) per-turn `<system-reminder>` attachment teaches the model to
       self-restrict (the load-bearing layer, ~95% of the policing); and
   (b) the permission pipeline degrades ask → deny when the model fails
       to self-restrict in headless mode ([permissions.ts:932](claude-code-source-code/src/utils/permissions/permissions.ts:932)).
   The API `tools` field stays mode-invariant — meaning the prompt cache
   PREFIX is preserved across NORMAL ↔ PLAN transitions. This is the
   real engineering insight: constraint enforcement that doesn't break
   caching is the difference between a toy and a production agent.

Both mechanisms also unblock future work: a plan-then-implement REPL
loop, a "summary of intent" surface for resume + checkpoint, and
analytics on completion rates.

# Design sketch

```
              ┌────────────────────────────────────────────────────┐
              │ AgentLoop (per-turn state)                         │
              │  - _todos: list[TodoItem]               ← M1       │
              │  - _todo_nudge: TodoNudge | None        ← M1       │
              │  - _permission_mode: PermissionMode     ← M2       │
              │  - _plan_mode_attachment: ...           ← M2       │
              │  ─────────────────────────────────────────────     │
              │  - _execute_one: soft-deny if mode==PLAN           │
              │                  and not tool.read_only ← M2       │
              └────────────────────────────────────────────────────┘
                      │                          │
                      │ Tool.read_only flag      │ per-turn nudge/attach
                      ↓                          ↓
        ┌──────────────────────────┐   ┌──────────────────────────┐
        │ tools.py                 │   │ context.py               │
        │  @dataclass class Tool:  │   │  ContextBuilder.build(   │
        │    read_only: bool=False │   │    snip_nudge=...,       │
        │  (per-tool declaration)  │   │    todo_nudge=...,       │
        │                          │   │    plan_mode_attachment=)│
        │  ToolRegistry.to_api_    │   │  prepends ALL as USER    │
        │  schema()  ← UNCHANGED   │   │  <system-reminder> dicts │
        │            (mode-invariant)│   │  in fixed front order   │
        └──────────────────────────┘   └──────────────────────────┘
                                                │
                          ┌─────────────────────┴────────────────────┐
                          │ Four attachment types share ONE inject   │
                          │ path (ATTACHMENT, ATTACHMENT_MEMORY,     │
                          │ ATTACHMENT_TODO_NUDGE, ATTACHMENT_       │
                          │ PLAN_MODE) → MessageType enum branch     │
                          │ in transcript.py / compact.py / context  │
                          │ + _coalesce_same_role merges adjacency.  │
                          └──────────────────────────────────────────┘
```

Three tools land in the registry (all M1/M2/M3 NEW; none deferred):

- `todo_write({todos: TodoItem[]})` — schema validates, replaces full
  list, collapses to `[]` when all completed. `read_only=True`. (M1)
- `enter_plan_mode({})` — flips `_permission_mode` to PLAN; returns
  the teaching text directly so model gets the instructions in
  tool_result. `read_only=True`. (M2)
- `exit_plan_mode({plan: str})` — calls injected `approval_callback`;
  on approval flips back to NORMAL, on rejection raises
  `PlanRejectedError` so `ToolExecutor` flags `is_error=True`.
  `read_only=True` (the tool is functionally read-only; the side
  effect is a state-machine transition, not a write). (M3)

Permission, prompt cache, and the read_only flag — M2's core idea:

```python
# tools.py — Tool dataclass gains ONE field
@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    fn: Callable[..., str]
    max_result_chars: int | None = MAX_RESULT_CHARS
    read_only: bool = False    # ← NEW. Each tool self-declares.

# permission.py — no filter function, just the enum + constants
class PermissionMode(StrEnum):
    NORMAL = "normal"
    PLAN = "plan"

ENTER_PLAN_MODE_TEACHING_TEXT = """Entered plan mode. ...
DO NOT write or edit any files yet. ..."""

# loop.py — _execute_one gains a 6-line pre-check
def _execute_one(self, call):
    if (self._permission_mode == PermissionMode.PLAN
            and not self._registry.get(call.name).read_only):
        return ToolResult(
            tool_use_id=call.id,
            content=f"Plan mode active: '{call.name}' is not allowed. ...",
            is_error=True,
        )
    # ... existing execute path UNCHANGED
```

What the model sees:

- In NORMAL mode: full tool schema, no attachment.
- In PLAN mode: **identical tool schema** (byte-equal `tools` field
  preserves the prompt cache PREFIX), plus a per-turn USER
  `<system-reminder>` attachment carrying the teaching text. If the
  model still calls a write tool, `_execute_one` returns
  `is_error=True` with a clear message → model sees soft-rejection
  and can self-correct without crashing the loop.

This is the resume soundbite: **constraint without cache breakage**.
The TS source enforces the same invariant via the same trick
([tools.ts:271-327 getTools](claude-code-source-code/src/tools.ts:271)
is mode-blind; [attachments.ts:1186 getPlanModeAttachments](claude-code-source-code/src/utils/attachments.ts:1186)
injects per-turn; [permissions.ts:932](claude-code-source-code/src/utils/permissions/permissions.ts:932)
degrades ask → deny in headless mode).

Bidirectional /plan slash (M3):

```python
# cli.py — /plan is a symmetric toggle, both directions silent
elif head == "/plan":
    if loop is None:
        print("Cannot toggle plan mode outside a loop.")
        return ""
    if loop._permission_mode == PermissionMode.NORMAL:
        loop._set_permission_mode(PermissionMode.PLAN)
        print("Plan mode entered. Write tools will be soft-rejected. "
              "Use /plan again to exit, or let the model call ExitPlanMode.")
    else:
        loop._set_permission_mode(PermissionMode.NORMAL)
        print("Plan mode exited. Write tools re-enabled.")
    return ""
```

Toggle is bidirectional + silent so the user can manually inherit the
read-only context (file snapshots, search results, todos) they
accumulated during planning, then continue in NORMAL — the transcript
history is preserved across the transition. ExitPlanMode tool is the
other exit path, with mandatory user approval — that one is for the
model to formally hand the plan back for sign-off.

CLI approval gate for ExitPlanMode (M3):

```python
def _confirm_exit_plan(plan_text: str) -> bool:
    print("\n--- Proposed plan ---")
    print(plan_text)
    print("---------------------")
    try:
        return input("Approve plan? (y/N): ").strip().lower() == "y"
    except (EOFError, KeyboardInterrupt):
        return False
```

# Risks / known unknowns

- **Tool.read_only audit completeness.** Every existing tool
  registration must be tagged `read_only=True` if (and only if) it has
  no externally observable side effect. Missing a True tag on a
  read-only tool degrades plan-mode utility (model can't explore); a
  False tag on a write tool is benign — it still gets soft-rejected.
  Failure mode: forgetting to tag `snip_history` (it mutates the
  transcript but only deletes redundant tool_results — already-snipped
  state) or `todo_write` as read_only=True silently restricts
  exploration in plan mode. M2 exit gate's "read_file in plan mode
  executes normally" assertion catches the obvious case; pair it with
  a registry-walk audit in tests.

- **Attachment ordering across four nudge types.** With M1 + M2,
  `ContextBuilder.build()` may prepend up to four user-role attachments
  on a single turn: file_snapshots, snip_nudge, todo_nudge,
  plan_mode_attachment. Order is fixed (file → snip → todo → plan →
  kept). `_coalesce_same_role` merges adjacency into one content list
  with this exact internal order preserved. Add a dedicated test in
  M2 verifying all four simultaneously: assert the merged content
  block is in front-to-back order. Existing coalesce regression
  tests (from ctx-mgmt-pdf-align M4 follow-up) cover two-attachment
  cases; four-attachment is new ground.

- **CLI input() blocks the loop on ExitPlanMode approval.**
  `_confirm_exit_plan` calls `input()` synchronously from inside the
  AgentLoop tool dispatch. In `--stream` mode this stalls the stream
  until the user answers. Acceptable for the replica (matches CC's
  modal approval UX); document as a Current Limitation in M3.

- **trace.py channel vocabulary expands from 9 to 11.** M1 adds `todo`
  (→ 10); M2 adds `permission` (→ 11). The "frozen at 9" invariant in
  CLAUDE.md needs a one-time update in M2's exit ritual. Be deliberate:
  document the expansion in CLAUDE.md trace.py per-file summary AND
  update test_trace.py's "no-raw-content" negative-case coverage to
  include both new channels.

- **Schema-strict providers (TodoWrite).** Some OpenAI-compatible
  endpoints enforce strict JSON schema; the TodoWrite item shape uses
  `min(1)` content which we encode as `"minLength": 1`. Confirm against
  DashScope qwen during M1's exit gate or note that strict-mode
  validation is provider-side.

- **Soft-deny noise from non-self-restricting models.** A model that
  ignores the plan_mode_attachment teaching and repeatedly attempts
  write tools will burn turn budget on soft-rejected ToolResults until
  `_max_steps` caps. This is acceptable (it's the same failure mode TS
  has under headless ask→deny), but document the budget-budget
  interaction in M2 and consider adding a metric
  `plan_mode_write_attempts` (already in the M2 metrics list) so a
  spike is visible.

# Out of scope (this initiative)

TodoWrite (M1):
- V2 Tasks suite (TaskCreate / TaskUpdate / TaskList / TaskGet / TaskStop
  / TaskOutput) — 6 tools, file persistence under `.tasks/`, `.highwatermark`
  + lockfile concurrency, swarm-shared task list, blocks/blockedBy DAG,
  owner field. Out-of-scope by design; V1 is the right size for a
  single-process replica.
- `shouldDefer: true` (TodoWriteTool.ts:51). Replica has no ToolSearch
  tool, so deferred lazy-load degrades to "directly load into schema".
- BRIEF mutex short-circuit (attachments.ts:3284-3289). No Brief tool here.
- Global `CLAUDE_CODE_DISABLE_ATTACHMENTS` env switch
  (attachments.ts:752-761). Replica uses per-mechanism enable flags.
- `verificationNudgeNeeded` branch (TodoWriteTool.ts:76-86). No
  verification agent in this replica.
- Per-(agentId | sessionId) todo namespacing (TodoWriteTool.ts:67).
  Single-agent replica, _todos is one instance field.
- TS's separate `TURNS_SINCE_WRITE` / `TURNS_BETWEEN_REMINDERS` knobs
  collapsed into one `TODO_REMINDER_TURNS` (both default to 10 in TS
  anyway; we trade tuning flexibility for KISS).

Plan Mode (M2 + M3):
- Plan file persistence to disk (TS plans.ts writeFile + getPlanFilePath).
- allowedPrompts (TS scoped-Bash permission requests in ExitPlanMode).
- Plan-mode reentry attachments (TS plan_mode_reentry message kind).
- Interview phase / pewter ledger growthbook variants (TS planModeV2.ts
  experiment branches).
- USER_TYPE=ant prompt variant for EnterPlanMode (ship the "external"
  prompt only).
- Slash command UI animations / progress bars.

# Anything else

> SIZING ASSESSMENT (informational): TodoWrite + Plan Mode jointly
> touch ~9 src files, introduce a cross-cutting PermissionMode that
> propagates through tools.py / loop.py / context.py / cli.py, and add
> ~30 test cases. Combining all of it in one milestone would replicate
> the observable-thresholds M1 thrash pattern. The 3-milestone split
> above respects every RUNBOOK heuristic (each M ≤6 src files, ≤4
> components touched per cross-cutting change, ≤15 new tests, no single
> M combines "introduce abstraction + wire everywhere + expose via
> CLI"). Phase 1 may re-assess but the split is intentional.

Resume narrative anchors (for the exit-ritual REVIEW.md to cite):

- M1: "Strict V1 TodoWrite replica — three load-bearing pieces (tool
  body, teaching prompt as system-prompt section, double-AND turn
  counter for stale-todo reminders) — plus a fourth attachment type
  (ATTACHMENT_TODO_NUDGE) that shares the same per-turn USER-role
  `<system-reminder>` injection path as file_snapshots, snip_nudge,
  and memory recall. Demonstrates that the four nudges in this
  replica aren't four ad-hoc one-offs; they're one abstraction
  applied four times."

- M2: "Constraint without cache breakage. Plan mode does NOT mutate
  the API `tools` field across NORMAL ↔ PLAN — instead it relies on
  (a) a per-turn `<system-reminder>` attachment teaching the model
  to self-restrict, and (b) a 6-line `_execute_one` pre-check that
  returns `is_error=True` when a non-`read_only` tool is invoked in
  plan mode. The prompt cache PREFIX stays stable. This mirrors TS
  exactly (tools.ts:271-327 getTools is mode-blind;
  attachments.ts:1186 injects per-turn; permissions.ts:932 degrades
  ask → deny in headless) — and is the difference between an agent
  that pays full prompt cost on every mode toggle and one that
  doesn't."

- M3: "Two exit paths with different semantics. ExitPlanMode (the
  tool) is the model's formal hand-off: CLI synchronously blocks on
  user approval, rejection raises PlanRejectedError → is_error=True
  so the model self-corrects. `/plan` (the slash) is a bidirectional
  toggle — silent, no approval — preserving the transcript history so
  the user can manually inherit the read-only context they accumulated
  during planning, then continue working in NORMAL. One path for
  model-driven completion, one for human override. Both lead to
  the same state-machine endpoint."

Source-mapping discipline: every new file lands with a docstring
pointing at the TS file + line range it mirrors, matching the
established replica convention (see snip_tool_model.py header).
