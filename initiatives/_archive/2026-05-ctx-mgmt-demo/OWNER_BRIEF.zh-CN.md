# OWNER BRIEF（中文）— ctx-mgmt-demo

> 本文档给项目 owner 阅读，重点是：这次交付了什么、如何演示、Before/After
> 有什么变化、哪些 finding 需要注意、以及如何把成果用于简历 / 面试表达。
>
> 英文归档审查（含评分卡、Tier A/B/C 决策、wrap-up 记录）见
> [`REVIEW.md`](./REVIEW.md)。

## 这次交付了什么

本次 `ctx-mgmt-demo` initiative 的核心目标，是把 P1–P9 已经写好、但「只有单元测试覆盖、真人在 CLI 里几乎看不到」的上下文管理机制（snip / externalize / full compact / microcompact），变成**可演示、可复跑、有真实 API 证据**的东西。按功能列出交付的具体能力：

- **`--microcompact-minutes N`（两个 REPL 都支持）** — 把 `MicroCompactor.threshold_minutes` 暴露成 CLI flag，走「显式 flag > `--aggressive-thresholds` 预设 > 内置默认 60」三级优先级；`N=0` 表示「任意时长都触发」，让 microcompact 不必在 notebook 里干等 60 秒。证据：commit `cda6f2b`，`src/simple_coding_agent/cli.py`（argparse 定义 + `_resolve_threshold` 接线）、`compact.py`（guard 从 `<1` 放宽到 `<0`）。
- **`--max-turns N`（仅 `simple-agent-openai --repl`）** — REPL 在第 N 个用户轮后走和 `/exit` 完全相同的干净退出路径（dump SessionMemory、退出码 0），slash 命令不计入轮数。作用是让真实 API 会话能被脚本无人值守地驱动到结束并落盘 artifact。证据：commit `cda6f2b`，`openai_cli.py` 的 `--max-turns` 定义 + `cli._drive_repl_session` 顶部的轮数计数器。
- **真实 API artifact 捕获脚本 + 3 套捕获产物** — 新增 SDK 驱动脚本 `demo/_scripts/capture_scenario.py`，对真实 DashScope API（模型 `qwen3.6-plus`）跑 3 个场景，每个场景落 4 个 artifact（transcript.txt / trace.stderr / metrics.json / stats_output.txt）。证据：commit `5d82e4d`，产物在 `demo/_artifacts/01_tool_result_management/`、`02_full_compact/`、`03_microcompact/`。
- **3 个逐机制讲解 notebook + README** — 每个 notebook 嵌入真实捕获输出（trace 行 / metrics / transcript 片段）、给出 `file:line` 源码映射、列出真实捕获命令、标注真实模型名。证据：commit `7c7496c`，`demo/README.md` 及 `demo/01_*.md`、`02_*.md`、`03_*.md`。
- **审核期修复的接线 bug（最重要的实质交付）** — 修好了一个早于本 initiative 就存在的接线缺陷：`_build_repl_loop` 把 `ToolResultStore` 接给了 `ContextBuilder` 却没接给 `AgentLoop`，导致**所有 REPL 会话的 `/stats` 里 `externalized bytes` 永远显示 0**（externalization 实际发生了，只是计数器没更新）。证据：commit `8ef0a4f`，`cli.py:510`（`loop_kwargs` 加一行 `"tool_result_store": tool_result_store`）+ 回归测试 `tests/test_repl.py::test_build_repl_loop_wires_tool_result_store_into_agent_loop`。

## 如何演示

下面分两类：**无需花钱**的演示（看 flag、跑测试、读已捕获产物）优先；真实 API 捕获命令会花钱，单列。

### 演示场景 A：确认两个新 flag 已上线（零成本）

```bash
$ python -m simple_coding_agent.cli --help | grep -A1 microcompact-minutes
  --microcompact-minutes N
                        MicroCompactor.threshold_minutes: clear compactable
...

$ python -m simple_coding_agent.openai_cli --help | grep -A1 -E "microcompact-minutes|max-turns"
  --microcompact-minutes N
  --max-turns N         REPL only: exit cleanly after exactly N user turns,
...
```

### 演示场景 B：跑测试，确认机制 + 接线修复都被钉住（零成本）

```bash
$ python -m pytest -q
........................................................................
820 passed in 8.50s

$ python -m pytest -q tests/test_repl.py -k wires_tool_result_store
.
1 passed ...
```

### 演示场景 C：直接读已捕获的真实 API 证据（零成本，最能说明问题）

```bash
$ cat demo/_artifacts/01_tool_result_management/trace.stderr
...
[trace] [snip] deleted=0 messages=11 snipped=2
[trace] [externalize] bytes=3800 tool_use_id=call_41d35f98ea5846429098f558
...

$ cat demo/_artifacts/02_full_compact/trace.stderr
[trace] [microcompact] cleared=0 messages=1
...
[trace] [compact] messages=13 post_tokens=299 pre_tokens=778 summarized=11
```

`snipped=2` = 两次旧 read 被折叠；`externalize bytes=3800` = 一个大结果被外置到磁盘；`compact ... summarized=11` = 11 条消息被压成一段摘要。三个 notebook（`demo/01_*.md` ~ `03_*.md`）逐行解释这些信号对应哪个机制。

### 演示场景 D：真实 API 捕获（会花钱，需 `.env` + DashScope key）

```bash
$ python demo/_scripts/capture_scenario.py 01   # snip + externalize
[capture] scenario=01 (01_tool_result_management) model=qwen3.6-plus
$ python demo/_scripts/capture_scenario.py 02   # full compact
$ python demo/_scripts/capture_scenario.py 03   # microcompact
```

每次会覆盖对应的 `demo/_artifacts/<scenario>/` 目录。模型可换（quota 用尽时改 `.env` 的 `SIMPLE_AGENT_MODEL`，候选见 `demo/README.md`）。

### 关于 reactive compact（无真实 API demo）

reactive compact（`PromptTooLongError` 后强制压缩并重试一次）在本 initiative 明确 OUT——触发它需要真把模型窗口撑爆，昂贵且模型相关。本机制为 MockProvider 演示：`python examples/stress_demo.py`，对应源码 `loop.py` 的 reactive 重试分支。

## Before / After 对比

| 项 | 之前（baseline `9ba662bf65e45d08949d4524203773a63bf36902`） | 之后（本 initiative 结束，HEAD `f937d8f`） |
| -------- | ---------------------------------- | ------------------- |
| microcompact 触发时长 | 写死「60 分钟」，notebook 里无法快速演示，只能干等 | `--microcompact-minutes N` 可配置，`N=0` 下一轮即触发 |
| 真实 API REPL 退出 | 只能手动 `/exit`，无法脚本化无人值守捕获 | `--max-turns N` 在 N 轮后自动干净退出（仅 openai REPL） |
| 上下文机制的真实证据 | 仅 1 个合并式 demo（`examples/visibility_full_demo.py`），无逐机制讲解 | 3 套真实 API 捕获 artifact + 3 个逐机制 notebook，reviewer 不跑也能读懂 |
| REPL `/stats` 的 `externalized bytes` | **永远显示 0**（接线 bug：store 没接进 `AgentLoop`），externalization 真发生了但计数器不动 | 已修复，`/stats` 和 `metrics.json` 都报真实字节数；加了回归测试钉住 |
| ruff 全仓库 | `demo/_scripts/capture_scenario.py` 带 10 个 ruff 错误（M2 误报「clean」，只跑了 `src tests`） | `ruff check .` 全绿 |
| pytest | 816 passing | 820 passing（M1 +3，审核回归测试 +1）；mypy 干净 |

## 用户视角下的关键 finding

* **REPL `/stats` 的 externalized bytes 曾长期为 0（接线 bug）** — 严重度 MEDIUM — 来源：main-agent reconciliation / code-reviewer / HANDOFF Section 5

  * 这是本次最值得 owner 知道的实质问题。`_build_repl_loop` 之前只把 `ToolResultStore` 接给了 `ContextBuilder`，没接给 `AgentLoop`，于是 `AgentLoop._tool_result_store=None`、`_refresh_externalized_bytes()` 直接短路，**任何 REPL 会话的 `/stats` 里 externalized bytes 都恒为 0**。注意：externalization 本身一直在正常工作（`[trace] [externalize] bytes=3800` 是证据），坏的只是那个对外计数器。**已在审核期修复**（`8ef0a4f`，加一行接线 + 一个回归测试），现在 `/stats` 和 `metrics.json` 一致。需要 owner 知道的原因：`demo/_artifacts/` 里的 canonical artifact 是修复**之前**捕获的，所以 `stats_output.txt` 仍显示 `externalized bytes: 0` 而 `metrics.json` 显示 `3800`——这不是数据矛盾，notebook 01 已写明此事，重跑会两边都显示 `3800`。

* **microcompact「invocations≠clears」容易被误读** — 严重度 LOW — 来源：M3 设计说明 / notebook 03

  * 场景 03 的 `microcompact_invocations=3` 但 `cleared=0`。原因是 `MicroCompactor` 的 `keep_recent=5`（默认值，**不受** `--aggressive-thresholds` 影响）保护了这个 2 轮会话里唯一的 tool result。这是正确行为，不是 bug：invocations 数的是「触发判定为真」的次数，不是「真清掉内容」的次数。notebook 03 已如实区分两者。owner 对外讲时不要把它说成「清理了 3 次」。

## 简历 / 面试可以怎么讲

* **亮点：复刻了 Claude Code 的上下文管理流水线并用真实 LLM 验证可观测性**

  * 可以怎么说：「实现了 snip / externalize / full-compact / microcompact 四类上下文压缩机制，并用真实大模型 API（DashScope `qwen3.6-plus`）跑出端到端证据，把每个机制的 trace 事件、`/stats` 计数器、transcript 片段都落盘成可复跑的 artifact。」
  * 证据：`demo/_artifacts/*/trace.stderr` 真实捕获行（如 `[trace] [compact] ... summarized=11`）+ `demo/01_*.md`~`03_*.md` notebook。
  * 不要夸大成：不要说「实现了完整的 Claude Code」——本项目不含 UI、MCP server、Anthropic 原生 provider，且 memory demo 被推迟。

* **亮点：在 code review 中发现并修掉了一个真实的可观测性接线 bug**

  * 可以怎么说：「在审核阶段定位到一个 metrics 接线缺陷——`ToolResultStore` 没接进 `AgentLoop`，导致 `/stats` 的 externalized bytes 恒为 0；用一行修复 + 一个共享同一 store 的回归测试钉住了它。」(keyword: regression test, dependency wiring)
  * 证据：commit `8ef0a4f`，`tests/test_repl.py::test_build_repl_loop_wires_tool_result_store_into_agent_loop`。
  * 不要夸大成：不要说「修了一个会丢数据的严重 bug」——它只影响一个统计计数器的展示，externalization 功能本身一直正常。

* **亮点：把硬编码阈值改造成可配置 CLI flag，遵循既有三级优先级约定**

  * 可以怎么说：「把 microcompact 的触发阈值从写死的 60 分钟改造成 `--microcompact-minutes` flag，复用代码库已有的『显式 flag > 预设 > 默认』三级优先级，未引入新抽象。」(keyword: precedence resolution, additive API)
  * 证据：commit `cda6f2b`，`cli.py` 的 `_resolve_threshold` 调用 + `compact.py` 的 guard 放宽。
  * 不要夸大成：不要说「重构了配置系统」——只是在既有 `_resolve_threshold` 模式上加了一个 key。

* **亮点：测试驱动 + 文档即证据的工程纪律**

  * 可以怎么说：「全程保持 820 测试通过、mypy 干净、`ruff check .` 全绿；每个交付的 demo 都用真实捕获的 artifact 支撑，notebook 里的每条输出都能在 `_artifacts/` 里找到原文。」(keyword: evidence-based docs)
  * 证据：`python -m pytest -q` → 820 passed；`ruff check .` → All checks passed。
  * 不要夸大成：不要给一个笼统的「覆盖率 90%+」数字——本次没有产出新的覆盖率报告，只能讲测试数和静态检查全绿。

## 还需要补什么

1. **统一 CLAUDE.md 里「at most once per loop instance」的过时措辞** — `loop.py` 的 per-file 摘要（CLAUDE.md 第 15 行）和 P5 roadmap（第 73 行）都说 microcompact「每个 loop 实例至多一次」，但实际 guard 按「最新 assistant 消息的 uuid」判定，REPL 里同一 loop 实例跨多轮会多次触发（场景 03 的 `microcompact_invocations=3` 就是反证，notebook 03 是对的）。其中一处在受保护的 Implementation Roadmap 段（RUNBOOK 禁止自动改），需人工统一两处措辞。已在 REVIEW.md 作为 proposal 记录。
2. **补一个「真正清理」的 microcompact 演示场景** — 当前场景 03 是教学性的（`cleared=0`，只演示触发与 keep_recent 保护）。可加一个跑 6+ 次 `read_file` 的场景，让超出 `keep_recent=5` 的旧结果真被清掉，从而展示 `cleared>0` 的效果。
3. **把 memory 模块纳入 demo** — 本 initiative 明确把 memory demo 推迟（PLAN 写明 memory 层需先加固）。memory 是面试里很有说服力的一块，值得在加固后补一套同样标准的 notebook + 真实 artifact。
4. **补齐 PROGRESS 的 M2 计数记录** — M2 的 PROGRESS 块只记了 `snip_invocations=2 / externalized_bytes=3800`，同一次运行的 `metrics.json` 还显示 `full_compacts=2`、`microcompact_invocations=1`（notebook 01 已如实写全）。PROGRESS 是 append-only 已提交文件，仅作记录，后续可在新块里补注。

## 项目状态一句话

本次 initiative 在 `9ba662b..HEAD` 范围共 8 个 commit，最终 pytest 820 通过（baseline 816，+4），mypy + ruff（`src tests` 与全仓库 `ruff check .`）全绿。完整审核结论见 `REVIEW.md`。
