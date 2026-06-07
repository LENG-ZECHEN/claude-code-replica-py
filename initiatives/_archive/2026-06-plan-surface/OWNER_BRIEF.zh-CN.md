# OWNER BRIEF（中文）— plan-surface

> 本文档给项目 owner 阅读，重点是：这次交付了什么、如何演示、Before/After
> 有什么变化、哪些 finding 需要注意、以及如何把成果用于简历 / 面试表达。
>
> 英文归档审查（含评分卡、Tier A/B/C 决策、wrap-up 记录）见
> [`REVIEW.md`](./REVIEW.md)。

## 这次交付了什么

按功能分类，本次 `plan-surface` initiative 在 baseline `17e616d` 之上交付了 3 个用户可见能力 + 1 套观测/治理基础设施。

- **TodoWrite V1（声明式待办列表 + 自动催办）** — 给模型注册了一个 `todo_write` 工具，模型可以声明会话级 todo 列表（pending/in_progress/completed 三态），全部完成后自动折叠。空闲 ≥10 个 assistant 回合时通过 `ATTACHMENT_TODO_NUDGE` user 消息提醒模型重新审视计划。证据：`src/simple_coding_agent/todo.py:1`、`src/simple_coding_agent/todo_tool.py:1`、commit `e62e928`。
- **Plan Mode（计划模式 + 软拒绝）** — 引入 `PermissionMode.NORMAL/PLAN` 状态机和 `Tool.read_only` 字段。模型调用 `enter_plan_mode` 后进入 PLAN，所有写工具（`write_file` / `run_shell` / `write_memory_entry`）在 `_execute_one` 被软拒绝返回 `is_error=True`（`src/simple_coding_agent/loop.py:880-894`），读工具（`read_file` / `list_files` / `search_text` / `todo_write` / `snip_history`）照常工作。关键架构：API `tools` schema 不随模式改变，prompt cache 前缀保持稳定。证据：`src/simple_coding_agent/permission.py:1`、commit `75eac7c`。
- **ExitPlanMode + `/plan` 双向切换** — 模型可以调用 `exit_plan_mode(plan=...)`，CLI 同步 `input("Approve plan? (y/N): ")` 阻塞等待人工审批；批准则回到 NORMAL，拒绝抛 `PlanRejectedError` 让模型自纠错。用户可用 `/plan` 斜杠命令静默双向切换 PLAN↔NORMAL（保留 transcript），无需走审批闸门。证据：`src/simple_coding_agent/plan_mode_tools.py:115-125`、`src/simple_coding_agent/cli.py:672-694`、commit `edd25d0`。
- **统一的 attachment 抽象 + 观测面** — `ContextBuilder.build()` 现在能在同一回合按固定顺序 prepend 四种 USER `<system-reminder>` 附件（file_snapshots / snip_nudge / todo_nudge / plan_mode_attachment），证明四个 nudge 是同一抽象的四个实例。`trace.py` 新增 `todo` 和 `permission` 两个频道（vocab 9→11），`metrics.py` 新增 6 个计数器。证据：`src/simple_coding_agent/context.py`、`src/simple_coding_agent/trace.py`、commit `e62e928`+`75eac7c`。

## 如何演示

### 演示场景 A：进入计划模式后写工具被软拒绝

```bash
$ simple-agent --repl
simple-agent REPL -- type /help for commands, /exit to quit.
> /plan
Plan mode entered. Write tools will be soft-rejected. Use /plan again to exit, or let the model call ExitPlanMode.

> /todos
(no todos)

> /plan
Plan mode exited. Write tools re-enabled.

> /exit
```

`/plan` 在 NORMAL↔PLAN 之间静默切换，每次切换都会在 `--verbose` 时打印 `[trace] [permission] mode=plan source=slash` 一行；transcript history 在切换时保留。

### 演示场景 B：查看 todo 列表 + 关闭 nudge 机制

```bash
$ simple-agent --repl --no-todo-reminder
> /todos
(no todos)

$ simple-agent --repl --todo-reminder-turns 3
# （--todo-reminder-turns 3 把 10 个回合的 nudge 周期压成 3 个；与 --no-todo-reminder 互斥）
```

两个 flag 同时支持 `simple-agent` 和 `simple-agent-openai`（M1 只在前者接线，review-fix `4efc445` 补齐了后者）。证据：`tests/test_openai_cli_repl.py`。

### 演示场景 C：完整的 plan-mode 工具链 + ExitPlanMode 审批闸

本场景需要真模型驱动；最小可复现路径是用 MockProvider 脚本化（`tests/test_repl_plan_mode.py` 已覆盖）：

```bash
$ pytest tests/test_repl_plan_mode.py -v
# 关键用例：
# - test_plan_slash_toggles_normal_to_plan
# - test_plan_slash_toggles_plan_to_normal_preserves_transcript
# - test_repl_exit_plan_mode_approval_flow_via_mockprovider
# - test_repl_exit_plan_mode_rejection_flow_via_mockprovider
$ pytest tests/test_plan_mode_soft_deny.py tests/test_exit_plan_mode.py -v
# 13 + 17 个用例覆盖软拒绝 + 审批/拒绝双分支 + 计数器接线
```

CLI 审批闸的真实交互形态可见 `src/simple_coding_agent/cli.py:_confirm_exit_plan`（在 `--stream` 下会同步阻塞，是已记录的 Current Limitation）。

## Before / After 对比

| 项 | 之前（baseline `17e616d`） | 之后（本 initiative 结束） |
| --- | --- | --- |
| 模型表达"我打算做什么" | 没有声明式机制，模型只能在文本里讲 | `todo_write` 工具 + 三态生命周期 + 自动折叠；UI 端 `/todos` 一键查看 |
| 防止模型在边研究边乱写文件 | 无任何手段 | `PermissionMode.PLAN` + 软拒绝；写工具返回 `is_error=True` 让模型自纠错，不会崩溃 |
| 计划被采纳的"signoff" | 无概念 | `exit_plan_mode(plan=...)` 工具 + CLI 同步审批 (`y/N`)；拒绝抛 `PlanRejectedError` |
| 用户手动进入/退出计划模式 | 不存在 | `/plan` 斜杠命令双向切换，保留 transcript 上下文 |
| Plan 切换是否破坏 prompt cache | 不适用 | NORMAL↔PLAN 之间 API `tools` 字节相同，cache 前缀稳定（`tests/test_enter_plan_mode.py` 用 deep-equal 钉死） |
| 观测面 | 9 个 trace 频道，无 todo/permission 频道 | 11 个频道（+`todo` +`permission`），6 个新 metric 计数器 |
| 测试规模 | pytest 835 | pytest 904 passed + 1 xpassed（+69，mypy/ruff 均 clean） |

## 用户视角下的关键 finding

- **HIGH（已修复）`plan_mode_exits_rejected` 计数器原本是 dead code** — 来源：code-reviewer detail finding，修复 commit `4efc445`。
  - 解释：M3 把 `plan_mode_exits` 改成 `approved+rejected` 的计算属性，但拒绝分支只 raise，没有 bump 任何计数器；只有审批通过的分支会通过 `_set_permission_mode(NORMAL)` 顺带把 approved 加 1。结果是"被拒绝的 plan 数量"永远等于 0，未来要做"模型 plan 通过率"统计就抓不到分母。修复方法：`register_exit_plan_mode_tool` 现在接受 `metrics=` kwarg，由 `AgentLoop._register_tools` 和 `cli._build_repl_loop` 注入真实 collector。

- **MEDIUM（已修复）软拒绝消息丢了恢复指引** — 来源：code-reviewer detail finding，修复 commit `4efc445`。
  - 解释：M2 实现软拒绝时 ToolResult content 只说"Plan mode active: 'write_file' is not allowed."，没有告诉模型怎么走出去。对那种不自觉自我克制的模型（PLAN 文档里专门点名的 failure mode），会在剩下的 turn budget 里反复撞墙耗费 token。修复后消息明确写了"Use exit_plan_mode to submit your plan for approval, or use /plan to exit plan mode manually."

- **MEDIUM（已修复）`simple-agent-openai` 缺失 `--no-todo-reminder` / `--todo-reminder-turns` flag** — 来源：code-reviewer detail finding，修复 commit `4efc445`。
  - 解释：M1 在 PLAN 文档里把这两个 flag 列为"两个 REPL 都支持"，但实际上只在 MockProvider 那条接了线。真实模型 REPL（OpenAI 兼容）下传 `--no-todo-reminder` 会 argparse 报错退出。这个差异会在演示真模型时直接撞错。

- **LOW（已修复）`transcript.normalize_for_api` 漏掉两类 attachment** — 来源：code-reviewer detail finding，修复 commit `4efc445`。
  - 解释：`compact.py` 的过滤名单里已经有 `ATTACHMENT_MEMORY` 和 `ATTACHMENT_TODO_NUDGE`，但 `transcript.normalize_for_api` 只过滤了 `ATTACHMENT_PLAN_MODE`。这意味着如果未来加 session 持久化或者其他经过 transcript 序列化的路径，可能会把 `<system-reminder>` body 当 user 消息泄回 API。已和 compact 名单同步对齐。

- **LOW（延后）`_todo_nudge` 每个内回合都会重复 prepend** — 解释：行为正确，只是 inner-turn 反复 build 时会多花一点 token；修复需要先确认 cache 失效语义，所以延后到下个 initiative。建议下一步：第一次成功 `build()` 后清掉 `_todo_nudge`。

- **LOW（延后）`record_plan_mode_exit` 把 `/plan` 手动退和 ExitPlanMode 工具通过混在一起** — 解释：`plan_mode_exits_approved` 同时包含人工切换和模型审批通过两种情况，做留存率统计时分不清"模型主动 hand-off"和"用户手动接管"。建议下一步：拆 `_approved` / `_manual` 两个字段并从 `_set_permission_mode` 传 `source`。

- **LOW（延后）`_set_permission_mode(PLAN)` 不是幂等的** — 模型重复调 `enter_plan_mode` 会重复计 `plan_mode_entries`。影响很小，建议下一步：开头加 `if self._permission_mode == mode: return`。

## 简历 / 面试可以怎么讲

* **亮点**：在 Python 复刻里完整还原了 Claude Code 的 Plan Mode permission 子系统
  * **可以怎么说**：实现了 NORMAL/PLAN 两态权限模型 + `Tool.read_only` 元数据 + per-turn `<system-reminder>` attachment 教模型自我约束 + ToolExecutor 层"软拒绝"安全网；mirroring 了上游 TS 源码"不在 schema 层 filter tools, 而是 prompt-driven self-restriction + runtime soft-deny" 的双层设计（reference: `tools.ts:271-327` getTools 是 mode-blind）。
  * **证据**：`src/simple_coding_agent/permission.py`、`src/simple_coding_agent/loop.py:878-894`、`tests/test_enter_plan_mode.py` 用 deep-equal 钉死了 NORMAL↔PLAN 之间 API `tools` 字节相同。commit `75eac7c`+`edd25d0`。
  * **不要夸大成**："设计了一套权限系统" —— 是 port 上游设计，不是原创设计。

* **亮点**：保持 prompt cache 前缀稳定的约束机制
  * **可以怎么说**：关键观察是 "constraint without cache breakage" — 如果 plan mode 走"在 schema 层 filter tools"，那每次 mode 切换都会让 prompt cache prefix 失效，agent 每个 turn 都会付全价 token。实际做法是 schema 完全不变，靠 (1) per-turn user `<system-reminder>` 教 model 自我约束 + (2) ToolExecutor 6 行 pre-check 兜底。这个 trade-off 是 production agent 跟 toy agent 的分界。
  * **证据**：`tests/test_enter_plan_mode.py::test_tools_schema_byte_identical_across_normal_and_plan_mode`、`src/simple_coding_agent/permission.py` 文档段、PLAN.md "Resume narrative anchors"。
  * **不要夸大成**：不要说"提升了 LLM 性能" — 这个保的是 token cost 不破，不是 latency 或 accuracy。

* **亮点**：四种 attachment 共享同一注入路径，证明抽象是真的抽象
  * **可以怎么说**：之前已有 `ATTACHMENT`（文件快照）、`ATTACHMENT_MEMORY`（记忆召回）、`snip_nudge`。本次新增 `ATTACHMENT_TODO_NUDGE` 和 `ATTACHMENT_PLAN_MODE` 后，`ContextBuilder.build()` 用一条固定顺序前置链 (`[file_snapshots, snip_nudge, todo_nudge, plan_mode_attachment, ...kept]`) + `_coalesce_same_role` 合并相邻同 role 消息处理。验证了"四个 nudge 不是四个 one-off, 是同一个 abstraction 用了四次"。
  * **证据**：`src/simple_coding_agent/context.py`、`docs/plan-mode.md`、`docs/todo.md`。
  * **不要夸大成**：不要说"重构了 context pipeline" — 是沿用已有 pattern 加新成员，不是大改。

* **亮点**：多层 tool 注册 pattern (no-op default → loop rewires → REPL re-injects)
  * **可以怎么说**：`exit_plan_mode` 在 `build_default_registry` 注册成 no-op，让 unit tests 不需要 loop 就能 import；`AgentLoop._register_tools()` 用真实的 `mode_setter` 闭包覆盖；`cli._build_repl_loop` 再用 `_confirm_exit_plan` 闭包覆盖一次。三层叠加完全靠 `ToolRegistry.register()` silent overwrite。这是一个"有意为之的非 bug"的设计，已经写成 ADR-0004 留作 future contributor 的护栏。
  * **证据**：`docs/DECISIONS/0004-noop-default-tool-factory-then-loop-rewires.md`、`src/simple_coding_agent/tool_registry_factory.py`、`src/simple_coding_agent/loop.py:620-628`。
  * **不要夸大成**：不要把它说成"全新的依赖注入框架" — 就是闭包 + 覆盖式注册。

* **亮点**：rigorous review-fix loop 修补了 4 个 review-time finding
  * **可以怎么说**：在 M3 之后跑了一轮 multi-agent code review（reviewer + doc-curator），把 1 个 HIGH（计数器 dead code）+ 2 个 MEDIUM（软拒绝丢恢复指引、openai_cli 缺 flag）+ 1 个 LOW（filter 名单不同步）全部修掉并加了 5 个回归测试；同时 sync 了 CLAUDE.md/README.md per-file summary 并写了 ADR-0004。最终 pytest 904 passed, mypy/ruff clean。
  * **证据**：commit `4efc445`、`1e242b5`；`initiatives/_archive/2026-06-plan-surface/REVIEW.md`。
  * **不要夸大成**：不要说"我们建了全自动 review 流水线" — 是手工运行 review skill 后人工 reconcile + 修，不是 CI 自动化。

## 还需要补什么

1. **拆 `plan_mode_exits_approved` 的"模型 vs 人工"** — 影响后续 plan 接受率统计的可信度 — 加 `_approved` / `_manual` 两个字段，从 `_set_permission_mode` 传 `source`。
2. **`_set_permission_mode(PLAN)` 幂等护栏** — 避免模型 spam-call `enter_plan_mode` 时 `plan_mode_entries` 虚高 — 函数开头 `if self._permission_mode == mode: return`。
3. **`_todo_nudge` 内回合重复 prepend** — 多 inner-turn 场景下小幅多花 token — 第一次成功 `build()` 后 `self._todo_nudge = None`，但要确认 cache 失效路径。
4. **`_confirm_exit_plan` 在 `--stream` 下同步阻塞** — 已记录为 Current Limitation，但若想支持 streaming UI 需要把 approval 路径异步化（worker thread + future）。
5. **Phase 2A exit-gate 加 `ruff check .` 输出抓取** — M2 PROGRESS 报告 "ruff: clean" 但实际带了 16 个 ruff 错（被 M3 顺手清掉），属于 process 漏洞 — 在 `run_all_milestones.sh` 的 exit gate 里强制引用 `ruff check .` stdout 而不是凭报告字段判定。

## 项目状态一句话

本次 initiative 在 `17e616d..HEAD` 范围共 6 个 commit（bootstrap + M1/M2/M3 + review-fix + review-doc），最终 pytest 904 passed + 1 xpassed（baseline 835，+69），mypy + ruff 全绿。完整审核结论见 [`REVIEW.md`](./REVIEW.md)。
