# Benchmark 4 — SM-compact Latency (dual-arm)

Generated: 2026-06-14T18:31:40.801074+00:00
Runs per arm: 50

## Deterministic arm (no API, reproducible floor)

> Source: deterministic: RuleBasedSummarizer recompute vs SessionMemorySummarizer reuse, perf_counter, no network

### Full summarization (RuleBasedSummarizer recompute)

- median: **0.399 ms**
- p90:    0.449 ms
- min:    0.251 ms
- max:    0.627 ms

### SM warm reuse (SessionMemorySummarizer, O(0))

- median: **0.291 ms**
- p90:    0.397 ms
- min:    0.222 ms
- max:    0.505 ms

### Speedup (deterministic floor)

- full / reuse = **1.4×** (median)
