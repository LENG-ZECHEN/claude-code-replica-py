# OWNER BRIEF（中文）— session-memory-dream

> 本文档给项目 owner 阅读，重点是：这次交付了什么、如何演示、Before/After
> 有什么变化、哪些 finding 需要注意、以及如何把成果用于简历 / 面试表达。
>
> 英文归档审查（含评分卡、Tier A/B/C 决策、wrap-up 记录）见
> [`REVIEW.md`](./REVIEW.md)。

## 这次交付了什么

本 initiative `session-memory-dream`（commit 范围 `094cf90..0d721ac`，共 11 个提交、pytest 由 912 增至 1016 + 1 xpassed）补齐了 Claude Code v2.1.88 中 context/memory 管线的最后两块缺失能力 —— 会话内存 (SM) 复用式压缩 与 跨会话 dream 合并 —— 并把背后的"分叉子智能体"机制抽出为一个可复用基础设施。所有交付的代码 mypy --strict + ruff 干净。

- **通用 ForkedAgentRunner 基础设施 (M1)** — 把原先散在 `ExtractMemoriesRunner` 内部的"分叉子智能体"（独立 messages、独立 system、白名单工具、固定上限轮数、写入限定在指定目录）抽取为通用类，并以 per-call `can_use_tool(name, input) -> (allow, reason)` 闸门取代旧的工具名白名单。顺带修复了一个真实 bug：旧实现把 `base_messages` 存进字段但从未发送给 sub-agent。证据：`src/simple_coding_agent/forked_agent.py`、commit `19020cd`。
- **SessionMemoryState + 增量 9 段 fold (M2)** — frozen dataclass 持有正在累积的 9 段摘要（与 `RuleBasedSummarizer` 对齐），`update_session_memory(state, new_messages)` 是一个纯函数：返回新 state、不可变；`SessionMemorySummarizer` 实现既有的 `Summarizer` Protocol，warm 状态下 `summarize()` 直接返回预热文本、**零次** provider 调用，cold 状态降级到注入的 fallback（Rule/LLM）。证据：`src/simple_coding_agent/session_memory_state.py`、`src/simple_coding_agent/compact.py` 中新增的 `SessionMemorySummarizer`、commit `c824b49`。
- **将 session-memory 接入 loop 与跨进程持久化 (M3)** — 新增 `--session-memory` 开关（默认关，向 `--extract-memories` 对齐）；`AgentLoop._run_stop_hooks` 每轮后调用 `maybe_update_session_memory` 同步增量 fold（替代 TS 的 fire-and-forget 后台抽取，这是已记录的 divergence）；`AgentLoop._force_compact` 在 try/finally 中把 `_compactor.summarizer` 临时换成 `SessionMemorySummarizer`，warm 路径下 zero LLM 摘要调用，cold 直接走回原 summarizer（null-vs-throw 契约不崩溃）。`session_store.load_session` 改返 3-tuple `(Transcript, CompactSummary | None, SessionMemoryState)`，老 session 文件因 key 可选仍然可加载。证据：`src/simple_coding_agent/loop.py`（`_run_stop_hooks` + `_force_compact`）、`src/simple_coding_agent/extraction_hooks.py::maybe_update_session_memory`、`src/simple_coding_agent/session_store.py`、commit `00dfea2`。
- **SM-compact 可观察性 + 双臂延迟基准 (M4)** — `MetricsCollector` 新增 `sm_compact_reuses` / `sm_compact_misses` 计数器（review-fix 后只在 `--session-memory` 开启时记录 miss，见下文 finding）；既有 11 通道 trace 词表保持冻结，在 `compact` 通道追加 `reused=<bool>` 字段；新增 `benchmarks/bench_sm_compact_latency.py` 双臂基准 —— (a) 确定性臂：`RuleBasedSummarizer` 全量重算 vs warm 复用，无网络可复现下限；(b) 真实 API 臂：在 `--confirm-api-call` + DashScope key 下测量 `LLMSummarizer` 实际延迟 vs ~0 复用。证据：`src/simple_coding_agent/metrics.py`、`src/simple_coding_agent/loop.py::_force_compact`、`benchmarks/_results/04_sm_compact_latency.{json,md}`、commit `97300de`。
- **consolidation_lock 五闸级联 (M5)** — 复刻 TS `autoDream.ts:125-189` + `consolidationLock.ts` 的"先便宜后昂贵"五闸级联：enabled → time (lock mtime 距今 ≥ 24h) → scan throttle (10 min) → session 数 (≥ 5 session) → PID lock。锁文件 `.consolidate-lock` 同时承担"PID 互斥"与"lastConsolidatedAt"两个角色（mtime 即时间戳，没有平行 state 文件，这是源代码的核心 invariant）。所有时间戳走依赖注入，测试零真实 sleep。证据：`src/simple_coding_agent/consolidation_lock.py`、commit `7ee0228`。
- **DreamConsolidator 4 阶段引擎 (M6)** — `provider != None` → 走 `ForkedAgentRunner` + 移植自 `consolidationPrompt.ts` 的 Orient/Gather/Consolidate/Prune+Index 4 阶段 prompt（含反 turn-waste 指令），工具闸门只允许只读 + 在 memory_dir 内写；`provider is None` → 走确定性回退：Jaccard 阈值 `HIGH_JACCARD_THRESHOLD=0.80` 去重（保留 mtime 最新）+ 超过 `MANIFEST_MAX_ENTRIES=200` 时按 mtime 最旧裁剪。所有写入走 `ProjectMemory.save/delete`，secret + path-traversal 保护原封不动。第二次跑保证幂等。证据：`src/simple_coding_agent/dream.py`、commit `346f555`。
- **`simple-agent memory dream` CLI + `--dream-on-exit` REPL 开关 (M7)** — CLI 默认 dry-run：先 `shutil.copytree` 复制 memory dir 到 `TemporaryDirectory`，在副本上把闸门全部置零跑一次，输出 `dream (dry-run): planned merged=N pruned=M`，真目录字节不变；`--apply` 走真实五闸级联；`--apply --force` 把 `min_hours=0, min_sessions=0, last_scan_at_ms=0` 全部置零；`--provider openai` 构造 `OpenAIProvider`（review-fix 后默认 `qwen-plus-latest` 而不是 DashScope 不提供的 `gpt-4o`）。`--dream-on-exit` REPL 开关（默认关）在 `/exit` / EOF / max-turns 三条退出路径里走一次 `_run_dream_on_exit()`，由 `_dream_fired` 一次性闸门保护。`MetricsCollector` 同时新增 `dream_runs / dream_merged / dream_pruned`。`consolidation_lock.record_consolidation(lock_path, now_ms)` 放进 `DreamConsolidator.consolidate()` 末尾，让"gate + run + stamp"在一个方法里自洽。同 ADR-0005 一并记录"无 cron / 无 async"divergence。证据：`src/simple_coding_agent/memory_cli.py`（`_cmd_dream`、`_dry_run_dream`、`_make_dream_provider`）、`src/simple_coding_agent/loop.py::_run_dream_on_exit`、`src/simple_coding_agent/cli.py::_exit_session`、`docs/DECISIONS/0005-dream-cli-no-cron-divergence.md`、commit `5730e78`。
- **诚实性修复 + 文档同步（review 阶段）** — review-fix `13761bd` 把 `sm_compact_misses` 改为只在 SM 开启时记录，并把 dream CLI 的 OpenAI 默认模型从 `gpt-4o` 改为 `qwen-plus-latest`；review-doc `0d721ac` 在 `CLAUDE.md` 补充 `forked_agent.py` / `session_memory_state.py` per-file 摘要 + 本 initiative 的 Implementation Roadmap 段落，并在 `README.md` 增加 `--session-memory` / `--dream-on-exit` / `simple-agent memory dream` 三段说明。证据：commit `13761bd`、commit `0d721ac`。

## 如何演示

下列命令均可在 `python-replica/` 下原样跑。前置：`pip install -e ".[dev]"` 已执行。

### 演示场景 A：dream CLI 默认安全（dry-run 不写盘）

```bash
$ mkdir -p /tmp/sm-dream-demo && export SIMPLE_AGENT_MEMORY_DIR=/tmp/sm-dream-demo
$ simple-agent memory add note redis-rate-limit "Redis token bucket rate limiting"
$ simple-agent memory add note redis-throttle "Redis token bucket rate limiting"
$ simple-agent memory dream
dream (dry-run): planned merged=1 pruned=0 — no files written (use --apply)

$ ls /tmp/sm-dream-demo
# 两个 .md 文件仍然在场，dry-run 字节不变
```

### 演示场景 B：dream CLI --apply --force（实际合并）

```bash
$ simple-agent memory dream --apply --force
dream applied: merged=1 pruned=0 written=0

$ simple-agent memory list
# 仅剩 mtime 更新的那条 — Jaccard ≥ 0.80 的近似项被去重
```

### 演示场景 C：SM 复用让 _force_compact 跳过 LLM 摘要

`simple-agent --repl --session-memory` 启动后正常对话，到达 `ContextBudget` 阈值时 `_force_compact` 会优先复用 warm `SessionMemoryState`：

```bash
$ simple-agent --repl --session-memory --verbose
# 经过若干轮触发 auto-compact 后 stderr 会看到：
[trace] [compact] reused=True
# 输入 /stats 可见：
# sm_compact_reuses=1
# sm_compact_misses=0
```

无人工 REPL 时可用 `tests/test_loop_session_memory.py` 验证同一契约（warm SM → MockProvider 调用次数 delta=0）。

### 演示场景 D：双臂延迟基准（确定性下限 + 真实 API headline）

```bash
$ python benchmarks/bench_sm_compact_latency.py --runs 50
# 写入 benchmarks/_results/04_sm_compact_latency.{json,md}
# 当前已 commit 的产物：
#   Full summarization (RuleBasedSummarizer recompute):   median 0.399 ms
#   SM warm reuse (SessionMemorySummarizer, O(0)):        median 0.291 ms
#   Speedup (deterministic floor): 1.4×

# 真实 API 臂（会花真钱、需要 DashScope key）：
$ python benchmarks/bench_sm_compact_latency.py --confirm-api-call --runs 20
```

### 演示场景 E：内部 refactor / unit-test 直观验证

部分功能（如 M1 ForkedAgentRunner 通用化、M2 `SessionMemoryState` 不可变 fold、M5 闸门级联）为内部实现改造，没有直接 CLI demo；可通过以下命令验证：

```bash
$ pytest tests/test_forked_agent.py tests/test_session_memory_state.py \
         tests/test_session_memory_summarizer.py tests/test_loop_session_memory.py \
         tests/test_consolidation_lock.py tests/test_dream_consolidator.py \
         tests/test_memory_cli_dream.py tests/test_bench_sm_compact.py -v
```

## Before / After 对比

| 项 | 之前（baseline `094cf90`） | 之后（本 initiative 结束 `0d721ac`） |
|---|---|---|
| 简历声称的 "98.7% 节省 compaction 时间" | 代码层面**没有依据**（无 SM 复用、无基准） | 由 `benchmarks/bench_sm_compact_latency.py` 双臂基准给出**带来源标注**的数字（确定性下限 1.4×；真实 API 臂在 DashScope 上可测） |
| 简历声称的 "auto-dream" | 仅是延后的 TODO，无任何实现 | 完整的 5-gate 级联 + 4 阶段 LLM prompt + Jaccard 确定性回退 + CLI 触发器 |
| ForkedAgentRunner 通用基础设施 | 不存在；`ExtractMemoriesRunner` 是单点实现，且有 `base_messages` 未发送的真实 bug | `forked_agent.py::ForkedAgentRunner` 通用化，per-call `can_use_tool` 闸门；`ExtractMemoriesRunner` 改为薄包装；context_messages 真实注入 |
| `_force_compact` 在压缩点的 LLM 调用 | 必然走一次 `Summarizer.summarize()`（可能是 LLM） | `--session-memory` 开启且 warm 时 zero LLM 调用；cold 仍走原 summarizer，绝不崩溃 |
| memory dir 跨会话合并 | 无；entries 持续单调增长，只能手动 `simple-agent memory delete` | `simple-agent memory dream`（dry-run 默认）+ `--apply` + `--apply --force`；`--dream-on-exit` REPL 触发 |
| Trace 通道词表 | 11 个频道冻结 | 仍是 11 个频道（无新增）；`compact` 频道追加 `reused=<bool>` 字段，词表 invariant 不破 |
| 测试规模 | pytest 912 passing (+1 xpassed) | pytest 1016 passing (+1 xpassed)，mypy --strict + ruff 全程干净 |
| 文档与可发现性 | `forked_agent.py` / `session_memory_state.py` / 新 CLI 标志在 CLAUDE.md / README 不可见 | CLAUDE.md 新增两个 per-file 摘要 + 本 initiative 的 roadmap 段落；README 增加三段 CLI 行为说明；ADR-0005 记录 no-cron divergence |

## 用户视角下的关键 finding

- **`.consolidate-lock` 写在 `memory_dir.parent` 下** — 严重度 MEDIUM — 来源：main-agent reconciliation (M-#2)
  - 当用户用环境变量 `SIMPLE_AGENT_MEMORY_DIR=/foo/memory` 自定义 memory 目录时，lock 文件实际落在 `/foo/.consolidate-lock`，**不在 memory_dir 内部**。如果用户的部署把 memory dir 单独挂出来或权限收紧，lock 可能写不进去或漏出预期范围。当前为有意延后修复（动它要回过头改 M5 的所有测试），但 owner 需要知道 lock 不在 memory dir 里。位置：`src/simple_coding_agent/loop.py:651`、`src/simple_coding_agent/memory_cli.py:269`。
- **当前 session 也会被算进 ≥5 session 闸门** — 严重度 MEDIUM — 来源：main-agent reconciliation (M-#3)
  - CLI 触发的 dream 与 `--dream-on-exit` 都没有传入 `current_session_id`，意味着评估"距上次 consolidate 以来动过几个 session"时把本次也算上了。对正常使用没大问题（只是闸门略宽松），但与 TS 源精确语义有出入。当前为有意延后（M6 已冻结 `DreamConsolidator.consolidate()` 签名）。
- **`--dream-on-exit` 静默绕过所有闸门** — 严重度 MEDIUM — 来源：main-agent reconciliation (M-#5)
  - `_run_dream_on_exit` 把 `min_hours=0, min_sessions=0, last_scan_at_ms=0` 都写死了。这是有意设计（"退出即合并"），但 PLAN 中"`fires one dream at REPL /exit`"的措辞并没明说要绕过闸门。Owner 演示时短会话也会立即合并，要意识到这是 by-design。若不希望短会话也合并，建议未来加一个 `--dream-on-exit-respect-gates` 类的 flag 或修订 ADR-0005。
- **若干"导出但未真正接入"的限制** — 严重度 LOW — 来源：M2/M3/M6 HANDOFF known-limitations 与 main-agent reconciliation
  - `update_session_memory_llm` 已实现并测试，但 stop-hook 没调它（每轮仍走确定性 fold）；
  - `update_session_memory` 是"先取新摘要，再回退到旧值"的简单 overwrite，不在 section 内累加（M3 LLM updater 可以更丰富，但未被默认接通）；
  - LLM 模式下 `dream_merged` 计数其实是工具调用次数，不是语义级合并次数；
  - `_dream_fired` 在 `consolidate` **运行前**就被设置，等价于失败也算"已尝试"（比文档承诺更强、不会重复触发）；
  - `_force_compact` 临时改写 `_compactor.summarizer`，本身是同步 replica 设计，不是 thread-safe（同步 sideQuery 同样设计，所以是一致的）。
  - 这些都不是阻塞性问题；后续如有产品化需要可按以上顺序优先级处理。

## 简历 / 面试可以怎么讲

- **亮点**：在不可改源的前提下，把 Claude Code v2.1.88 的会话内存压缩 + 跨会话 dream 合并两块缺失能力补齐到 Python replica，并提供带来源标注的延迟基准
  - **可以怎么说**："Built two missing context-management mechanisms (warm session-memory compaction reuse + cross-session memory dream consolidation) on a Python replica of Claude Code v2.1.88, including a dual-arm latency benchmark that replaced a previously unbacked '98.7%' claim with disclosed perf_counter numbers."
  - **证据**：`src/simple_coding_agent/{forked_agent,session_memory_state,consolidation_lock,dream}.py`、`benchmarks/bench_sm_compact_latency.py`、commit 范围 `094cf90..0d721ac`
  - **不要夸大成**：不要说"在 Anthropic Claude Code 主仓里加了 X"或"性能提升 100×" —— 这是一个**对照源代码移植 + 在 OpenAI-compatible 环境下的可观察基准**，确定性下限只有 1.4×；真实 API 臂在 DashScope 上才会显著放大。
- **亮点**：抽出通用 ForkedAgentRunner，同时修复了已存在的 base_messages 未发送 bug
  - **可以怎么说**："Refactored a single-purpose sub-agent (memory extraction) into a generic ForkedAgentRunner reusable across 3 callers (extract_memories, LLM session-memory updater, dream consolidator) with per-call path-scoped tool gating instead of name-only whitelisting; fixed an existing context-injection bug in the process."
  - **证据**：`src/simple_coding_agent/forked_agent.py`、commit `19020cd`、`tests/test_forked_agent.py` (+11 cases)
  - **不要夸大成**：不要把它说成"通用 AI agent 框架"；它只是这个 replica 内部的多回合 sub-agent 抽象。
- **亮点**：用闸门级联 + lock-as-state-file 复刻分布式定时合并机制
  - **可以怎么说**："Replicated a faithful 5-gate cascade (enabled → time → scan-throttle → session count → PID mutex) for periodic memory consolidation, where the lock file's mtime doubles as the lastConsolidatedAt timestamp — single-source-of-truth, no parallel state file."
  - **证据**：`src/simple_coding_agent/consolidation_lock.py`、`tests/test_consolidation_lock.py` (+18 cases)、commit `7ee0228`
  - **不要夸大成**：这是单机 / 单 memory dir 级的同步实现，不是分布式系统；本 replica 同步、不是真正后台线程。
- **亮点**：完整 ADR 与 known-limitations 风格的工程纪律
  - **可以怎么说**："Documented intentional divergences from the TS source (no cron / no async event loop / lock placement at memory_dir.parent) in ADR-0005 and CLAUDE.md Current Limitations rather than silently approximating; every milestone has an exit gate + a frozen-contract block carried in HANDOFF.md."
  - **证据**：`docs/DECISIONS/0005-dream-cli-no-cron-divergence.md`、`CLAUDE.md` 的 Current Limitations 段、`initiatives/current/HANDOFF.md`
  - **不要夸大成**：不要说"100% 复刻了 TS 行为"；本 initiative 显式记录了至少 3 类有意 divergence。
- **亮点**：一致性的安全姿态（默认 dry-run、闸门可置零、metrics 可观察）
  - **可以怎么说**："Shipped the dream subcommand with a safe default posture: dry-run via shutil.copytree + TemporaryDirectory so the real memory dir is byte-identical, --apply required to write, --apply --force only for demo, and dream_runs/merged/pruned counters surfaced via /stats."
  - **证据**：`src/simple_coding_agent/memory_cli.py::_dry_run_dream`、`src/simple_coding_agent/metrics.py`、`tests/test_memory_cli_dream.py` (+13 cases)、commit `5730e78`
  - **不要夸大成**：不要说"零数据丢失风险"；`--apply` 仍然会真删；这是承诺**默认**安全，不是承诺**任何调用**都安全。

## 还需要补什么

1. **把 `current_session_id` 与 lock 位置两个 MEDIUM finding 修掉** — 这两条是离 TS 源最接近一致性 / 用户预期的小裂缝，影响窗口很窄但能写进下一个 initiative 的 brief — 建议下一步：起一个微 initiative（≤3 文件、≤10 test）传递 `current_session_id` 并把 lock 移到 memory_dir 内（同时更新 M5 测试期望）。
2. **把 `--dream-on-exit` 的"绕过所有闸门"行为显式 ADR 化** — 既然 M-#5 是 by-design，最干净的做法是在 ADR-0005 末尾追一段或起 ADR-0006 把行为写进合同 — 建议下一步：单独一条 docs commit，不动代码。
3. **接通 `update_session_memory_llm` 到 stop-hook（可选开关）** — 当前 LLM updater 在每轮 fold 时不被调用，使得 LLM 模式实际只在压缩点偶发生效；如要把 SM warm reuse 在真实 API 模式下也展示更显著的节省，需要一个 `--session-memory-mode llm` 类型的 flag — 建议下一步：M3.5 风格的小 initiative，先把 flag 加上，再用 `benchmarks/bench_sm_compact_latency.py` 的真实 API 臂出一份对比数据。
4. **`dream_merged` 在 LLM 模式下的语义** — 当前统计的是 sub-agent 工具调用次数而非实际语义合并条数；要给 LLM 模式一个更可靠的报表数字，需要做一次"前后 entry diff"计算 — 建议下一步：放进后续 dream 改进的 backlog，不影响当前 demo 的诚实性（已在 limitations 里披露）。
5. **跑一次 DashScope 真实 API 臂并把数据 commit 进 `benchmarks/_results/`** — 当前 commit 进仓库的数字仅是确定性下限；演示 / 简历时如果想展示更显著的 speedup，缺一份真实 API 数据 — 建议下一步：付费跑一次 `python benchmarks/bench_sm_compact_latency.py --confirm-api-call --runs 20`，把生成的 markdown 报告作为可引用证据 commit 进仓库。

## 项目状态一句话

本次 initiative 在 `094cf90..HEAD` 范围共 10 个 commit（再加 1 bootstrap = 11），最终 pytest 1016 通过（baseline 912，+104），mypy + ruff 全绿。完整审核结论见 `REVIEW.md`。
