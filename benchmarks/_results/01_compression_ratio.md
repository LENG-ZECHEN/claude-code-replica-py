# Benchmark 1 — Compression Ratio at ~100K-token Scale

Generated: 2026-05-25T06:40:57.210749+00:00

## Configuration

- Tool exchanges seeded: **30** (each tool_result = 14,000 chars)
- Total seeded: **420,000 chars** ≈ **105,000 estimated tokens**
- ContextBudget: max_tokens=10,000, reserved_output=2,000
- ContextCompactor: keep_recent=4, threshold=0.5

## Result

- Compaction fired: **True**
- Messages summarized: **87**
- Pre-compact tokens:  **107,508**
- Post-compact tokens: **3,601**
- Tokens saved:        **103,907**
- **Compression ratio: 96.65%**

## MetricsCollector snapshot

- full_compacts: 1
- microcompact_invocations: 0
- snip_invocations: 1
- reactive_compacts: 0
- externalized_bytes: 0
- tokens_per_turn: [4218]

- AgentLoop status: `completed`
