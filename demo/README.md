# Context Management Demo

Three per-mechanism notebooks demonstrating the context-management pipeline of
`simple_coding_agent` against the real DashScope API. Each notebook walks through one
mechanism, embeds captured trace events and `/stats` counters, and maps every observable
to its source location.

---

## Notebooks

| File | Mechanism | One-line summary |
|------|-----------|-----------------|
| [01_tool_result_management.md](01_tool_result_management.md) | Snip + Externalize | Older reads of the same file are folded to a sentinel; a 3 800-byte result is offloaded to disk and replaced with a pointer |
| [02_full_compact.md](02_full_compact.md) | Full compact | Token growth crosses the 0.2× threshold on a 4 000-token window; 11 messages are summarized into one compact narrative |
| [03_microcompact.md](03_microcompact.md) | Microcompact | With `--microcompact-minutes 0`, microcompact fires 3 times; `keep_recent=5` protects the single tool result so `cleared=0` throughout |

### Complementary material

- **`examples/visibility_full_demo.py`** — a single combined real-API run that exercises
  compact, microcompact, snip, and externalize in one session and persists four artifacts
  under `examples/_artifacts/`. Use it to see all mechanisms together; use the notebooks
  above to understand each in isolation.
- **`examples/stress_demo.py`** — MockProvider-only demo for **reactive compact** (the
  `PromptTooLongError` retry path). Reactive compact is provider-independent error recovery:
  the agent force-compacts and retries the same turn exactly once when the provider rejects
  the context as too long. Because triggering a real "context too long" error requires filling
  the model's entire window (expensive and model-specific), the mock demo is the correct
  surface for that mechanism. Run it with `python examples/stress_demo.py`.

---

## Re-running the captures

### Environment

The artifacts in `_artifacts/` were produced from `python-replica/.env`. That file must
contain:

```
DASHSCOPE_API_KEY=<your key>
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
SIMPLE_AGENT_MODEL=<model name>
```

Do not use `env.sample` — the real `.env` is pre-configured and is the only file the capture
script reads.

### Command

From `python-replica/`:

```console
python demo/_scripts/capture_scenario.py 01   # snip + externalize
python demo/_scripts/capture_scenario.py 02   # full compact
python demo/_scripts/capture_scenario.py 03   # microcompact
```

Each command overwrites the corresponding `_artifacts/<scenario>/` directory.

### About the canonical artifacts

The `_artifacts/` directories checked into this repo are **one canonical run** using
`qwen3.6-plus`. Re-runs will vary in exact transcript text, trace field values, and token
counts, but counter-level assertions (`full_compacts >= 1`, `snip_invocations >= 2`,
`microcompact_invocations >= 1`) hold regardless of model or run-to-run variation.

### Model swap — if your default model's quota is exhausted

If `SIMPLE_AGENT_MODEL` exhausts its quota mid-capture, edit `.env` and switch to one of
these alternatives (all reachable through the same `OPENAI_BASE_URL`):

```
qwen3-coder-plus-2025-09-23
glm-5
deepseek-v3.2
qwen-plus-latest
qwen-long-latest
```

Re-run the failing scenario after the swap. The `# model: <name>` header in
`stats_output.txt` will reflect whichever model actually produced that artifact.

---

## Environment variables consumed

| Variable | Purpose |
|----------|---------|
| `DASHSCOPE_API_KEY` | DashScope API key (also accepted as `OPENAI_API_KEY`) |
| `OPENAI_BASE_URL` | Provider base URL — `https://dashscope.aliyuncs.com/compatible-mode/v1` for DashScope |
| `SIMPLE_AGENT_MODEL` | Model name passed to `OpenAIProvider` (e.g. `qwen3.6-plus`) |
