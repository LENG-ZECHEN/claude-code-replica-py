# Benchmark 3 — Real-API Token-Cost Comparison

Generated: 2026-05-25T07:21:14.436898+00:00
Model: `qwen-plus-latest`  ·  Prices (USD per 1M tokens): in=$0.11, out=$0.28 (`model-table`)

## Scenario

- Seeded transcript: **8** tool exchanges × 6,000 chars each
- Driven turns:      **5**
- Full pipeline:     compactor ON + tool-result-store ON + microcompact ON, budget=8,000 tokens
- Naive baseline:    compactor OFF + tool-result-store OFF + microcompact OFF, budget=200,000 tokens

## Token & cost totals

| Variant | Calls | Input tokens | Output tokens | Total USD |
| ------- | ----- | ------------ | ------------- | --------- |
| full    | 5 | 10,659 | 437 | $0.001295 |
| naive   | 5 | 64,429 | 423 | $0.007206 |

## Savings

- Input tokens saved:  **53,770** (83.46%)
- Output tokens saved: **-14** (-3.31%)
- USD saved:           **$0.005911** (82.03%)

## Per-call token traces

### full

```json
[
  {
    "input": 1869,
    "output": 154,
    "cache_read": 0,
    "cache_create": 0
  },
  {
    "input": 2052,
    "output": 74,
    "cache_read": 0,
    "cache_create": 0
  },
  {
    "input": 2153,
    "output": 49,
    "cache_read": 0,
    "cache_create": 0
  },
  {
    "input": 2224,
    "output": 115,
    "cache_read": 0,
    "cache_create": 0
  },
  {
    "input": 2361,
    "output": 45,
    "cache_read": 0,
    "cache_create": 0
  }
]
```

### naive

```json
[
  {
    "input": 12646,
    "output": 129,
    "cache_read": 0,
    "cache_create": 0
  },
  {
    "input": 12804,
    "output": 63,
    "cache_read": 0,
    "cache_create": 0
  },
  {
    "input": 12894,
    "output": 76,
    "cache_read": 0,
    "cache_create": 0
  },
  {
    "input": 12992,
    "output": 79,
    "cache_read": 0,
    "cache_create": 0
  },
  {
    "input": 13093,
    "output": 76,
    "cache_read": 0,
    "cache_create": 0
  }
]
```
