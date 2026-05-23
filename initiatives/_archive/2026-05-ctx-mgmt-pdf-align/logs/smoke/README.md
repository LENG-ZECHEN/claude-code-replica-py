# Live smoke-test evidence — ctx-mgmt-pdf-align follow-up

Captured 2026-05-24 during the post-review follow-up (commits `38645d0`–`7559692`).
These are raw outputs from running the real-provider CLI against a live
OpenAI-compatible endpoint — **DashScope `qwen3.6-plus`** (`OPENAI_BASE_URL` +
`DASHSCOPE_API_KEY` from the project `.env`). They back the claims in
[`../../REVIEW.md`](../../REVIEW.md) "Post-review follow-up → OpenAI live smoke run".

No secret is present in any file (the API key lives in `.env`, is never echoed;
verified by scan before commit). The workspaces themselves were throwaway dirs
under `/tmp` and are not preserved.

## Files

| File | Run | What it proves |
|---|---|---|
| `smoke2-aggressive-repl.out` / `.err` | Smoke 2 — `--aggressive-thresholds` REPL reading 3 files | `[compact]` + `[externalize]` traces fire live; the **P1 coalesced attachment payload is accepted** (exit 0, no API error); the model answers a post-compaction `MAGIC_TOKEN` question whose answer lived only in the re-injected recent-file snapshot (byte 6781, beyond the externalize preview) → M3 recent-file re-injection validated end-to-end. |
| `smoke3-snip-drive.verbose.err` | Smoke 3 attempt 1 (`--verbose`, no `/save`) | `[budget]` trace showing token growth across the two turns with **no full compact** (roomy default budget) — the regime the model-snip nudge needs. |
| `smoke3-snip-drive.out` | Smoke 3 attempt 2 (`/save` run) | Terminal output; model reports it snipped the eligible old tool results. |
| `smoke3-snipdrive.session.json` | Smoke 3 attempt 2 saved session | **Definitive audit-item (a) evidence:** contains `"name": "snip_history"` (the model emitted a valid model-driven snip call) and the tool result `Snipped 2 messages`, with no `snip refused`. |

## Commands (reconstructed)

```bash
# Smoke 1 (not captured to a file): one-shot wrap-survival check
python -m simple_coding_agent.openai_cli \
  "Read the file calc.py and tell me the exact value of MAGIC_TOKEN. Then stop." \
  -w <ws> --show-steps --no-stream --max-tokens 512

# Smoke 2: aggressive REPL -> compaction + recent-file re-injection (P1 payload)
printf '%s\n' \
  "Read calc.py and summarize it in one sentence." \
  "Read notes.txt and tell me the last line." \
  "Read data.txt and tell me roughly how many rows it has." \
  "Without re-reading any file, what is the exact value of MAGIC_TOKEN from calc.py?" \
  "/exit" \
  | python -m simple_coding_agent.openai_cli --repl --aggressive-thresholds \
      -w <ws> --verbose --no-stream --show-steps --max-tokens 512

# Smoke 3: model-driven snip via the new --snip-nudge-growth-tokens flag
printf '%s\n' \
  "Read f1.py .. f7.py one at a time using read_file, then tell me which file defines TARGET_FUNC." \
  "If you just received a system-reminder that you can free context by calling snip_history with old tool_result message uuids, call snip_history now with the snippable uuids it listed." \
  "/save snipdrive" \
  "/exit" \
  | SIMPLE_AGENT_SESSIONS_DIR=<sessions> python -m simple_coding_agent.openai_cli --repl \
      --snip-nudge-growth-tokens 500 -w <ws> --no-stream --max-tokens 512
```

## How to confirm the snip evidence

```bash
grep -o '"name": "snip_history"' smoke3-snipdrive.session.json
grep -o 'Snipped [0-9]* messages'  smoke3-snipdrive.session.json
```
