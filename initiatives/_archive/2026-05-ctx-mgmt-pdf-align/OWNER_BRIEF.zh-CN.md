# OWNER BRIEF（中文）— ctx-mgmt-pdf-align

> 本文档给项目 owner 阅读，重点是：这次交付了什么、如何演示、Before/After
> 有什么变化、哪些 finding 需要注意、以及如何把成果用于简历 / 面试表达。
>
> 英文归档审查（含评分卡、Tier A/B/C 决策、wrap-up 记录）见
> [`REVIEW.md`](./REVIEW.md)。

## 这次交付了什么

本次 initiative（`ctx-mgmt-pdf-align`）把项目的五机制上下文管理流水线对齐到 Claude Code v2.1.88 的 PDF 参考行为，按功能分四块交付：

- **microcompact 保留最近 5 条 + autoCompact 双余量阈值 + LLM 默认摘要器（M1）** — `MicroCompactor` 新增 `keep_recent=5`，冷缓存清理时保留 5 条最新可压缩 tool_result；`ContextCompactor.should_compact()` 改为「`used >= context_window - output_headroom(12k) - compact_headroom(20k)` 且 `used >= min_session_tokens(30k)`」的新公式（旧 ratio 作为第二个 OR 触发保留）；提供 `provider` kwarg 时默认切换到 `LLMSummarizer`。证据：commit `f4b9596`，`src/simple_coding_agent/compact.py`，4 个 CLI flag 见 `src/simple_coding_agent/cli.py`。
- **引擎 snip 真删除孤儿块与远古 cleared 对（M2）** — 引擎侧 `SnipTool.snip()` 从「折叠」升级为「删除」：删除配不上对的 orphan tool_use / tool_result，以及当累计 cleared 占位 token >= `ancient_cleared_threshold_tokens`(默认 10k) 时按最旧优先删除成对的 cleared 块，并插入一个 `SNIP_BOUNDARY` 标记。证据：commit `70be001`，`src/simple_coding_agent/snip.py`、`models.py`、`context.py`。
- **autoCompact 后回灌最近文件快照（M3）** — `read_file` 成功时捕获 `FileSnapshot`（path/content/captured_at，frozen），压缩后作为 `ATTACHMENT` 消息重新注入上下文，让模型无需重新读文件。`CompactSummary` 改为 frozen dataclass。证据：commit `646bf2c`，`src/simple_coding_agent/loop.py`、`compact.py`、`context.py`、`models.py`。
- **模型驱动的 snip_history 工具 + uuid 可见性 + 10k nudge（M4）** — 新注册 `snip_history` 工具，模型传入 `message_uuids` 删除过往 tool_result；`_normalize_messages()` 用 `<msg uuid="...">` 包裹 tool_result 让模型能看到 uuid；token 增长越过 10k 时注入 `SnipNudge` 提醒。证据：commit `02f17f6`，`src/simple_coding_agent/snip_tool_model.py`[新]、`tool_registry_factory.py`、`context.py`、`loop.py`。

整体质量：pytest 615 → 704（+89），mypy clean（22 个源文件），ruff clean。

## 如何演示

本项目默认执行路径不发起真实 API 调用（MockProvider / ShellMode.MOCK），以下命令均可离线运行。

### 演示场景 A：autoCompact 与 reactiveCompact 真实触发（覆盖 M1 阈值逻辑）

```bash
$ python examples/stress_demo.py
compact fired (messages_summarized=42)
[detail] pre_tokens=53763, post_tokens=3601
reactive compact fired (messages_summarized=0)
...
```

### 演示场景 B：microcompact 冷缓存清理触发（覆盖 M1 keep_recent）

```bash
$ python examples/microcompact_demo.py          # 时间戳回拨 120 分钟，触发
microcompact fired (results cleared=3)
$ python examples/microcompact_demo.py --fresh  # 新时间戳，跳过（负向路径）
microcompact skipped
```

### 演示场景 C：M1 新增的 4 个 CLI flag 真实存在

```bash
$ python -m simple_coding_agent.cli --help
... [--microcompact-keep-recent MICROCOMPACT_KEEP_RECENT]
    [--output-headroom OUTPUT_HEADROOM] [--compact-headroom COMPACT_HEADROOM]
    [--min-session-tokens MIN_SESSION_TOKENS] ...
```

### M2 / M3 / M4 — 无直接 CLI demo

- **M2 引擎 snip（orphan + ancient cleared 删除）** 为内部实现改造，无直接 CLI demo；可通过 `tests/test_snip.py`（M2 新增 15 个用例）验证。
- **M3 最近文件回灌** 无独立 demo；可通过 `tests/test_context.py` / `tests/test_loop.py` / `tests/test_models.py` 验证。
- **M4 model-driven snip_history** 没有专门的 example 脚本，也没有单独的 slash 命令；最直接的验证是 `python -m pytest tests/test_snip_tool_model.py`（16 个用例全绿）。注意：M4 的端到端「模型真的发出 snip_history 调用」路径在全 MockProvider 测试套件中未被真实 endpoint 验证（见下方 finding 2）。

## Before / After 对比

| 项 | 之前（baseline `8f1d98f`） | 之后（本 initiative 结束） |
| --- | --- | --- |
| microcompact 清理粒度 | 冷缓存时清空所有可压缩 tool_result | 保留最近 5 条，仅清更旧的（`keep_recent=5`） |
| autoCompact 触发阈值 | 单一 ratio（`used > available * threshold`） | 双余量公式（减 12k 输出 + 20k 压缩余量，配 30k 下限），旧 ratio 作为 OR 第二触发保留 |
| snip 对 orphan / cleared 块 | 仅折叠新鲜冗余结果，留占位 | 真删除孤儿块与远古 cleared 对，插入 `SNIP_BOUNDARY` |
| 压缩后最近文件 | 无；模型需重新 read_file | 压缩前快照 + 压缩后作为 ATTACHMENT 回灌，免重读 |
| snip 控制权 | 仅引擎硬编码 | 引擎 GC + 模型驱动 `snip_history` 工具共存 |
| 测试规模 | pytest 615 passing | pytest 704 passing（+89） |

## 用户视角下的关键 finding

* **M4 自报测试基线错误（phantom 685）** — 严重度 MEDIUM — 来源：code-reviewer，main-agent 已用 `git worktree` 独立核实
  * HANDOFF / PROGRESS / commit message 都写 M4 是「685 → 704 (+19)」，但 M3 结束 commit `646bf2c` 实际只 collect 670 个测试，所以真实增量是「670 → 704 (+34)」。整个区间真实序列是 615 → 632 → 647 → 670 → 704，「685」这个数从未出现过。M4 退出门槛（比 M3 多 ≥15）实际是满足的（+34），所以这是文档记账错误，不是质量门失败。建议：在 PROGRESS.md M4 块把基线改成 670，否则未来对账会困惑。

* **预置 attachment / nudge 可能产生连续同 role(user) 的 API 消息** — 严重度 MEDIUM — 来源：code-reviewer，main-agent 已读 `src/simple_coding_agent/context.py:278-281` 核实
  * `build()` 在 `_normalize_messages`（唯一做同-role 合并的地方）和 trim 之后，把 user-role 的 attachment / nudge dict 直接 prepend 到 payload 最前面。如果第一条 kept 消息也是 user-role，payload 开头就会出现相邻的多条 user 消息，绕过了同-role 合并。全 MockProvider 测试套件不向真实 endpoint 序列化，704 个绿测试看不到这个形状风险。HANDOFF Section 5 (a)/(b) 自己也标注需要一次 live smoke run。建议：用 `OpenAIProvider` 跑一次真实 smoke，确认 OpenAI 接受这种相邻 user 消息且不 strip `<msg uuid="...">`。

* **`evaluate_snip_request([])` 空列表会「成功」并触发空 replace_all** — 严重度 LOW — 来源：code-reviewer
  * 空 `message_uuids` 通过校验，返回「Snipped 0 messages」而不是报错；schema 没有 `minItems: 1`。这削弱了「用 refusal 教模型」的反馈闭环。建议：若后续打磨，给 schema 加 `minItems: 1` 或在工具 fn 里对空列表 refuse。

> 此外，main-agent 在收尾时已应用两处文档更新（owner 应知晓）：Tier A 在 `CLAUDE.md` 追加了 `snip_tool_model.py` 的逐文件摘要；Tier B 新建 ADR `docs/DECISIONS/0002-coexisting-engine-and-model-snip.md` 并在 `docs/DECISIONS/README.md` 追加索引行。另有两条 Tier C 建议未应用、留待人工评审：README 缺 `simple-agent` 的逐 flag 列表（M1 新增 4 个 flag 未文档化）、CLAUDE.md「Implementation Roadmap」缺本 initiative 的条目。

## 简历 / 面试可以怎么讲

* **亮点**：复刻并对齐了 LLM agent 的多机制上下文管理流水线（microcompact / snip / autoCompact / reactiveCompact）到一个参考实现的真实行为
  * **可以怎么说**：基于 Claude Code v2.1.88 的行为，对齐了五机制上下文管理流水线（context compaction pipeline），包括 microcompact 的 keep-recent 策略、autoCompact 的 double-headroom 阈值、压缩后最近文件回灌（recent-file re-injection）。
  * **证据**：commit `f4b9596`、`646bf2c`；`src/simple_coding_agent/compact.py`、`context.py`
  * **不要夸大成**：不要说「实现了 Claude Code」——这是 narrow-scope replica，不含 UI、MCP server、Anthropic SDK provider，也不含 forked-agent / prompt-cache-sharing 优化（明确 out of scope）。

* **亮点**：设计了「引擎 GC + 模型驱动」两种 snip 共存的架构
  * **可以怎么说**：实现了 deterministic 引擎侧 snip（GC orphan 块与远古 cleared 对）与 model-driven `snip_history` 工具的共存设计，模型可按 message uuid 选择性删除历史 tool_result。
  * **证据**：commit `70be001`、`02f17f6`；ADR `docs/DECISIONS/0002-coexisting-engine-and-model-snip.md`
  * **不要夸大成**：不要说「模型驱动 snip 已在生产 live 验证」——它只在 MockProvider 测试中验证，缺一次真实 OpenAI smoke run。

* **亮点**：以 immutable / 纯函数 + 强测试覆盖落地
  * **可以怎么说**：所有压缩/快照数据结构 frozen，`evaluate_snip_request` 等核心逻辑为无副作用纯函数；测试从 615 增长到 704（+89），mypy / ruff 全 clean。
  * **证据**：`python -m pytest -q`（704 passed）；`src/simple_coding_agent/snip_tool_model.py`
  * **不要夸大成**：覆盖增长是单元/集成测试，不含真实 endpoint 的 e2e；不要说「全链路 e2e 验证」。

* **亮点**：用「source-mapping」方式把每个设计决策追溯到 TS 原型的命名位置
  * **可以怎么说**：以 PDF 参考逐机制对齐，每个 milestone 在 notes 里引用具体 PDF section 与对应源位置，可追溯（traceable）。
  * **证据**：`initiatives/_archive/2026-05-ctx-mgmt-pdf-align/PLAN.md` 各 milestone 的 notes；`CLAUDE.md` 逐文件摘要
  * **不要夸大成**：PDF 是 user-owned 文档、不在 repo 里；不要声称「逐行对照官方源码」。

## 还需要补什么

1. **一次真实 OpenAI live smoke run** — finding 2 是 MEDIUM 且只能靠真实 endpoint 暴露（相邻 user 消息形状 + `<msg uuid>` 是否被 strip / 截断）— 用 `simple-agent-openai --repl` 跑几轮含 read_file + snip_history 的会话，抓 HTTP request body 确认。
2. **修正 PROGRESS.md / HANDOFF M4 的 phantom 685 基线** — 把 M4 块改成「670 → 704 (+34)」，避免历史记录对账困惑（已作为 Tier C 建议写入 REVIEW.md）。
3. **给 `snip_history` schema 加 `minItems: 1`** — 关掉「空列表 snip 0 条算成功」的反馈漏洞（finding 3），让 refusal 闭环完整。
4. **应用两条 Tier C 文档建议** — 给 README 补 `simple-agent` 逐 flag 列表（M1 的 4 个 flag 目前无文档），并在 CLAUDE.md Roadmap 补本 initiative 条目。
5. **为 M4 补一个可运行 example** — M2/M3/M4 都没有像 stress/microcompact 那样的离线 demo 脚本；给 snip_history 加一个 MockProvider 脚本能让对外演示更直观。

## 项目状态一句话

本次 initiative 在 `8f1d98f..HEAD` 范围共 5 个 commit（1 bootstrap + M1–M4），
最终 pytest 704 通过（baseline 615，+89），mypy + ruff 全绿。完整审核结论见
`REVIEW.md`。
