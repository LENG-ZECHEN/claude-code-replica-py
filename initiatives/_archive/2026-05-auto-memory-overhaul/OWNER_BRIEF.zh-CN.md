# OWNER BRIEF（中文）— auto-memory-overhaul

> 本文档给项目 owner 阅读，重点是：这次交付了什么、如何演示、Before/After
> 有什么变化、哪些 finding 需要注意、以及如何把成果用于简历 / 面试表达。
>
> 英文归档审查（含评分卡、Tier A/B/C 决策、wrap-up 记录）见
> [`REVIEW.md`](./REVIEW.md)。

> **后续修复说明（2026-05-25 补注，归档后经 owner 要求添加）**：下方「用户视角下的关键 finding」中的 4 个 MEDIUM「接好线没通电」问题，以及 ⑥/⑦/⑧ 三个 LOW 问题，均已在 `main` 修复（fix `212b6af`；文档同步 `8d20b1b` / `c373ee1`）。另两个 LOW（`provider.py` 超 800 行、`test_null_tracer` 过期陈述）暂未处理。原始 finding 文本作为历史记录保留；pytest 807 → 816，mypy + ruff 全绿。详见 [`REVIEW.md`](./REVIEW.md) 的 “Follow-up resolution” 一节。

## 这次交付了什么

按功能列出 `auto-memory-overhaul` 这次交付的具体能力（功能级，非文件级）。本 initiative 共 10 个 commit（`6aed9ec..HEAD`，最终 `e9aef6a`），把 replica 的记忆子系统从「JSON 存储 + 用户手动写 + Jaccard 同步读」推进到「`.md` + frontmatter 存储 + 模型自助写 + LLM selector 召回 + 自动抽取兜底」。

- **`.md` + YAML frontmatter 记忆存储** — `ProjectMemory.save()` 改为写 `<id>.md`，frontmatter 含 `name/type/description/created_at`；新增递归扫描 `scan_memory_files()`（按 mtime 倒序），`MEMORY.md` 索引带 200 行 / 25KB 截断与原子写。证据：commit `612487d`；`memory.py:197`（`to_md_text`）。
- **`migrate-format` CLI 子命令** — `simple-agent memory migrate-format` 把旧 `.json` 幂等转成 `.md`（已存在的 `.md` 跳过不覆盖），迁移期 `all()`/`load()` 同时读 `.json` 与 `.md`。证据：`memory_cli.py:145`（`_cmd_migrate_format`）；commit `612487d`。
- **`write_memory_entry` 工具（模型可在对话中自助写记忆）** — 校验 `type ∈ {user,feedback,project,reference}`、id 安全模式、`description ≤ 150` 字符、body 过密钥扫描，支持同 id upsert；每轮 quota=3，第 4 次写返回 `is_error=True`（`"memory write quota exhausted this turn (max 3)"`）。仅当 `ProjectMemory` 存在时才注册。证据：`coding_tools.py:493`（`write_memory_entry`）；commit `8c230ca`。
- **`## Memory Management` 系统提示教学段** — 在 `_build_system_prompt()` 中，于 CLAUDE.md 段与动态 `## Memory` snippets 之间插入约 250 token 的静态教学段（cache 前缀稳定），并让 `/remember` REPL 与工具路径共享同一个 `ProjectMemory` 实例。证据：commit `89ee8b4`。
- **`ExtractMemoriesRunner` 自动抽取引擎** — 纯类，5 轮内循环、工具白名单 `{read_file, list_files, search_text, write_memory_entry}`，返回 `ExtractionResult(written_paths, errors, turn_count)`；抽取写入隔离到本地 `ProjectMemory(memory_dir)`，逃不出主 agent 的存储。证据：`extract_memories.py:92`（`ExtractMemoriesRunner`）；commit `7830075`。
- **抽取 stop-hook + 7 层 gating + 计量** — `_run_stop_hooks` 在 `run()`/`run_stream()` 每次返回前触发 `maybe_extract_memories`，游标 `_last_memory_message_uuid` 只在成功时前进（异常保留，at-least-once）；两个 REPL 加 `--extract-memories`（默认关）和 `--extract-throttle N`（默认 1），`MetricsCollector` 加 `extract_invocations`/`extract_writes`。证据：`extraction_hooks.py`；`cli.py:1006`、`openai_cli.py:215`；commit `99afe34`。
- **`Provider.call_selector` + `memdir.py` 召回基础设施** — `Provider` 协议加 `call_selector`，`MockProvider` 支持脚本化 `selector_responses`，`OpenAIProvider` 用可配置 cheap model（默认 `gpt-4o-mini`、JSON 模式、temperature=0）；失败抛 `SelectorError`。新 `memdir.py` 导出 `format_memory_manifest`、`collect_recent_successful_tools` 与逐字 `SELECT_MEMORIES_SYSTEM_PROMPT`。证据：`provider.py`；`memdir.py`；commit `272e831`。
- **sideQuery LLM 召回 + ATTACHMENT 注入 + Jaccard 兜底** — `find_relevant_memories` 4 门控（开关 / 非空 / 多词 / session_bytes < 60KB），校验返回文件名防幻觉，`SelectorError` 回退到 Jaccard；`read_memories_for_surfacing` 每文件 ≤200 行 + ≤4KB 截断、带 staleness 头；命中结果包成 `<system-reminder>` 的 `ATTACHMENT_MEMORY`（USER 角色）注入。证据：`memdir.py`、`recall_hooks.py`、`models.py`（`ATTACHMENT_MEMORY`）；commit `e9aef6a`。

> 质量：pytest **807 passed, 0 failed, 0 skipped**（baseline 711，净增约 +96）；mypy 干净（26 个源文件）；ruff 干净。

## 如何演示

下面的命令均已在本机实跑验证，输出为真实片段。

### 演示场景 A：`.md` 记忆存储 + 旧 JSON 迁移（最清晰的新 CLI 面）

```bash
$ export SIMPLE_AGENT_MEMORY_DIR=/tmp/mem-demo   # 先放一个旧的 old-fact.json 进去

$ python -m simple_coding_agent.memory_cli migrate-format
Migrated 1 entries. Run again to verify (idempotent).

$ python -m simple_coding_agent.memory_cli migrate-format   # 再跑一次：幂等
Migrated 0 entries. Run again to verify (idempotent).

$ python -m simple_coding_agent.memory_cli list
old-fact	[user]	Old Fact
```

迁移后磁盘上同时保留 `old-fact.json` 与新生成的 `old-fact.md`，`.md` 内容形如：

```bash
$ cat /tmp/mem-demo/old-fact.md
---
name: Old Fact
type: user
description: user prefers tabs over spaces
created_at: 2026-01-01T00:00:00+00:00
---

user prefers tabs over spaces
```

（生产入口为 `simple-agent memory migrate-format` / `simple-agent memory list`，本机用 `python -m simple_coding_agent.memory_cli` 等价驱动。）

### 演示场景 B：手动写 / 查记忆

```bash
$ python -m simple_coding_agent.memory_cli add user py-style "always run ruff before committing"
saved memory py-style (user)

$ python -m simple_coding_agent.memory_cli show py-style
id:         py-style
name:       py-style
type:       user
...
always run ruff before committing
```

### 演示场景 C：开启自动抽取开关（标志真实存在，实际抽取需真 provider）

```bash
$ python -m simple_coding_agent.cli --help | grep extract-memories
  --extract-memories    Enable automatic memory extraction after each turn.
```

`--extract-memories` / `--extract-throttle N` 两个标志在 `cli.py` 与 `openai_cli.py` 上都已暴露（也可用环境变量 `SIMPLE_AGENT_EXTRACT_MEMORIES=1` / `SIMPLE_AGENT_EXTRACT_THROTTLE`）。注意：**默认关闭**，且只有对接真实 provider 时才会真正抽取，因为抽取要花主模型 token。

### 内部功能（无独立 CLI demo）

以下三项都在 agent 循环内部触发，**无独立 CLI demo**，请用测试验证：

- **`write_memory_entry` 工具**：`tests/test_loop_write_memory_e2e.py`、`tests/test_write_memory_tool.py`
- **7 层抽取 stop-hook**：`tests/test_extract_memories_e2e.py`、`tests/test_has_memory_writes_since.py`
- **sideQuery 召回注入 + Jaccard 兜底**：`tests/test_sidequery_recall.py`、`tests/test_loop_memory_injection.py`

一条命令跑通核心证据（本机已验证 31 passed）：

```bash
$ python -m pytest tests/test_loop_write_memory_e2e.py tests/test_extract_memories_e2e.py \
    tests/test_sidequery_recall.py tests/test_loop_memory_injection.py \
    tests/test_memory_migrate.py tests/test_write_memory_tool.py -q
31 passed
```

## Before / After 对比

| 项 | 之前（baseline `6aed9ec`） | 之后（本 initiative 结束） |
| --- | --- | --- |
| 记忆存储格式 | 每条 `<id>.json`，扁平 `# Memory Index` 标题，无 frontmatter | `<id>.md` + YAML frontmatter，递归子目录，`MEMORY.md` 索引带 200 行/25KB 截断 |
| 记忆写入路径 | 仅 CLI `memory add` + REPL `/remember`（都需用户手动） | 新增模型对话内 `write_memory_entry` 工具（带 quota） + 抽取子循环兜底（opt-in） |
| 记忆读取/召回 | 仅 Jaccard 同步选 top-5 | LLM selector（`call_selector`）选最相关项，失败回退 Jaccard；命中包成 `<system-reminder>` 注入 |
| 旧数据迁移 | 无 | `migrate-format` 幂等 JSON→MD，迁移期双读兼容 |
| 测试规模 | 711 passing | **807 passing**（净增约 +96） |

## 用户视角下的关键 finding

> **已修复（2026-05-25）**：下列 4 个 MEDIUM 问题与 ⑥/⑦/⑧ 三个 LOW 已在 `212b6af` 修复（详见文首说明 / `REVIEW.md`）；`provider.py` 行数、`test_null_tracer` 陈述两项 LOW 暂留。以下原文保留作历史记录。

核心主题：**「接好了线但实际没通电」（wired but inert）** —— 下面 4 项功能单测能过（单测直接用构造输入调纯函数），但在集成后的真实 turn 循环里**从不触发**。这些不影响主存/主写路径的正确性，但意味着对外讲时不能宣称这些读路径优化「端到端生效」。

* **`recent_tools` 在实循环里恒为 `[]`** — 严重度 MEDIUM — 来源：main-agent reconciliation
  * `inject_memory_attachments`（`loop.py:216`/`369`）在新用户消息 append（`loop.py:209`）**之后**才运行，`collect_recent_successful_tools`（`recall_hooks.py:48`）从尾部反扫先撞到那条新用户文本就返回 `[]`。结果：selector prompt 里那条「最近用过的工具」线索每轮都不触发。建议：把召回注入移到 append 用户消息之前，或显式传入上一轮工具列表。

* **`read_file_state` 去重集合从不被填充** — 严重度 MEDIUM — 来源：main-agent reconciliation
  * `loop.py:198` 初始化了这个集合，但**没有任何地方 `.add()`**。后果：主 agent 已经用 `read_file` 打开过的记忆，仍可能被重复 surface。建议：在 `read_file` 成功处把路径写进该集合。

* **`extraction_in_progress` 重入门是死代码** — 严重度 MEDIUM — 来源：main-agent reconciliation
  * `loop.py:548` 给 7 层门控的第 4 门传的是字面量 `False`；`loop.py:541/558` 上设的实例标志没有任何门读取。实际重入只靠第 1 门 `is_subloop` 兜住。HANDOFF Section 2 里「外层 check」的说法不准确。建议：把 `self._extraction_in_progress` 真正传进门控，或删掉这层声称的保护以免误导。

* **`memory_select` trace 恒报 `fallback_used=False` 且 `manifest_size == selected_count`** — 严重度 MEDIUM — 来源：main-agent reconciliation
  * `recall_hooks.py:59-65` 把这两个值写死了。后果：每次 selector 失败走 Jaccard 兜底时，trace 上的兜底信号都是错的，诊断/成本观测的价值被抵消。建议：从 `find_relevant_memories` 真实返回里透出 `fallback_used` 与原始 manifest 大小。

* **`write_memory_entry` 的 `tags` 参数被接受但从不落盘** — 严重度 LOW — 来源：main-agent reconciliation
  * `to_md_text`（`memory.py:197-207`）只序列化 `name/type/description/created_at`，**不写 `tags`**——尽管 dataclass 存了 tags、工具签名也收 tags。后果：一个有文档的工具参数是静默 no-op。建议：要么把 tags 写进 frontmatter，要么从签名/文档里去掉。

* **抽取器仍用 M4 的 manifest stub** — 严重度 LOW — 来源：main-agent reconciliation
  * `ExtractMemoriesRunner` 用 `_get_existing_manifest`（`extract_memories.py:84-89`，读 `MEMORY.md[:2000]` 字节前缀），没换成 M6 的 `format_memory_manifest(scan_memory_files(...))`。后果：抽取 prompt 的「不要重复已有记忆」提示可能是过期/被行截断的。建议：后续 initiative 改接 canonical manifest。

* **`provider.py` 已 867 行，超过本项目 800 行硬上限** — 严重度 LOW — 来源：main-agent reconciliation
  * M6 加 `call_selector` 时没拆分；有点讽刺，因为 M5/M7 为了把 `loop.py` 压到 ≤800 行专门拆了 `extraction_hooks.py`/`recall_hooks.py`。建议：把 selector 相关代码抽到独立模块。

* **HANDOFF/PLAN 关于 `test_null_tracer_zero_overhead` 失败的说法已过期** — 严重度 LOW（文档风险）— 来源：main-agent reconciliation
  * HANDOFF.md:155/188 与 PLAN provenance 称该测试 failing/quarantined，但本机全量套件 **807 passed, 0 skipped**，全绿。对外引用测试数时以实跑为准。

## 简历 / 面试可以怎么讲

下面均为可防守、不过度夸大的表达。

* **亮点**：为一个 Claude Code 的 Python 复刻实现了完整的记忆子系统升级（`.md`+frontmatter 存储、模型自助写工具、LLM 召回 + 词法兜底），并保持 100% 测试绿。
  * **可以怎么说**：用 7 个单关注点 milestone（M1–M7）把记忆模块从「JSON + 手动写 + Jaccard 读」演进到「Markdown+frontmatter 存储、模型可调用的 `write_memory_entry` 工具、LLM-selector 召回带 Jaccard fallback」，pytest 从 711 增至 807，mypy/ruff 全程干净。
  * **证据**：commit 范围 `6aed9ec..HEAD`（10 commits）；`memory.py`、`coding_tools.py:493`、`memdir.py`、`provider.py`。
  * **不要夸大成**：不要说「实现了端到端的语义记忆系统」——selector 默认对接 `gpt-4o-mini`，且若干读路径优化目前是 inert 的（见上）。

* **亮点**：安全/隔离意识贯穿写入路径。
  * **可以怎么说**：写记忆走 path-traversal 防御（`_SAFE_ENTRY_ID_PATTERN` + `is_relative_to`）、密钥 body 扫描、每轮 quota=3 防滥写、upsert-only 不暴露 delete；抽取子循环写入隔离到独立 `ProjectMemory` 实例，逃不出主存储。
  * **证据**：`coding_tools.py:493`；`tests/test_write_memory_tool.py`（quota/upsert/secret/registration 共 10 例）。
  * **不要夸大成**：不要说「做了完整威胁建模」——是针对性防御，非系统性安全评审。

* **亮点**：用 selector + 兜底的健壮召回设计，处理了 LLM JSON 模式不可靠的现实问题。
  * **可以怎么说**：sideQuery 召回先用 cheap model 选最相关记忆，校验返回文件名防幻觉，`SelectorError` 时优雅回退到原有 Jaccard selector，绝不让异常冒出主循环。
  * **证据**：`memdir.py`（`find_relevant_memories` / `_jaccard_fallback`）；`tests/test_sidequery_recall.py:147`（`test_selector_error_falls_back_to_jaccard`）。
  * **不要夸大成**：不要说「recent-tools 感知召回 / read-file 去重已生效」——这两条目前 inert（finding 1/3）。

* **亮点**：工程纪律——单关注点 milestone 拆分、向后兼容、文件行数预算。
  * **可以怎么说**：为守住 800 行硬上限，把 stop-hook 与召回编排分别抽到 `extraction_hooks.py` / `recall_hooks.py`；用 `migrate-format` + 双读窗口做零中断的存储格式迁移。
  * **证据**：`loop.py`（恰好 800 行）；`memory_cli.py:145`；`tests/test_memory_migrate.py`（幂等性测试）。
  * **不要夸大成**：不要说「所有文件都符合行数预算」——`provider.py` 现为 867 行，超限（finding 5）。

* **亮点**：诚实的工程交付——已知 inert 点被记录为 follow-up，而非掩盖。
  * **可以怎么说**：在 ADR-0003 与 CLAUDE.md 的 per-file 摘要里明确标注了「wired but inert」的 4 处问题与异步 sideQuery（M-ε）的延期决定。
  * **证据**：`docs/DECISIONS/0003-provider-selector-and-hook-module-extraction.md`；CLAUDE.md 中 `recall_hooks.py` / `extraction_hooks.py` 的 Caveat 段。
  * **不要夸大成**：不要把这些当「已修复」来讲——它们是已知待办。

## 还需要补什么

> **现状（2026-05-25）**：第 1–4 项已在 `212b6af` 全部完成（另含 ⑥/⑦/⑧ LOW 修复）；第 5 项文档大部分已补（roadmap 与模块行于 `8d20b1b`、NOW.md 于 `c373ee1`），仅 README 的 `migrate-format` 子命令说明仍未补。下列原始清单保留作历史。

按优先级排序：

1. **修正召回注入时机，让 `recent_tools` 真正生效** — 现在 selector 的「最近工具」线索每轮都空跑（finding 2）— 下一步：把 `inject_memory_attachments` 移到 append 新用户消息之前，或显式传上一轮工具列表，并加一个端到端断言 `recent_tools != []`。
2. **填充 `read_file_state` 去重集合** — 否则已读记忆会被重复 surface（finding 3）— 下一步：在 `read_file` 成功处 `.add()` 路径，并补一条「已读不重复 surface」的测试。
3. **修正 `memory_select` trace 的 `fallback_used` / `manifest_size`** — 当前写死导致兜底诊断信号失真（finding 4）— 下一步：从 `find_relevant_memories` 透出真实值再 `emit`。
4. **接通真正的重入门或删除死代码** — `extraction_in_progress` 门是死的，仅 `is_subloop` 兜底（finding 1）— 下一步：把实例标志真正传进 gate 4，并同步修正 HANDOFF 的「外层 check」描述。
5. **补齐文档（Tier C pending）** — `migrate-format` 子命令尚未写进 README；CLAUDE.md Implementation Roadmap 缺 `auto-memory-overhaul` 的 P-bullet；README 的 "Key concepts" / "Project structure" 表缺 4 个新模块行 — 下一步：在 review 之外单独补这几处文档。

## 项目状态一句话

本次 initiative 在 `6aed9ec..HEAD` 范围共 10 个 commit，最终 pytest **807** 通过（baseline 711，+96），mypy + ruff 全绿。完整审核结论（评分卡、Tier A/B/C 决策、wrap-up 记录）见 [`REVIEW.md`](./REVIEW.md)。
