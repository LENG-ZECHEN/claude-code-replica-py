# Benchmark 3 — Real-API Token-Cost Comparison

Generated: 2026-05-25T08:32:40.375156+00:00
Model: `qwen-plus-latest`  ·  Prices (USD per 1M tokens): in=$0.11, out=$0.28 (`model-table`)

## Scenario

- Seeded transcript: **8** tool exchanges × 6,000 chars each
- Driven turns:      **5**
- Full pipeline:     compactor ON + tool-result-store ON + microcompact ON, budget=8,000 tokens
- Naive baseline:    compactor OFF + tool-result-store OFF + microcompact OFF, budget=200,000 tokens

## Token & cost totals

| Variant | Calls | Input tokens | Output tokens | Total USD |
| ------- | ----- | ------------ | ------------- | --------- |
| full    | 5 | 10,511 | 446 | $0.001281 |
| naive   | 5 | 64,473 | 436 | $0.007214 |

## Savings

- Input tokens saved:  **53,962** (83.7%)
- Output tokens saved: **-10** (-2.29%)
- USD saved:           **$0.005933** (82.24%)

## Per-call token traces

### full

```json
[
  {
    "input": 1869,
    "output": 117,
    "cache_read": 0,
    "cache_create": 0
  },
  {
    "input": 2015,
    "output": 63,
    "cache_read": 0,
    "cache_create": 0
  },
  {
    "input": 2105,
    "output": 43,
    "cache_read": 0,
    "cache_create": 0
  },
  {
    "input": 2170,
    "output": 160,
    "cache_read": 0,
    "cache_create": 0
  },
  {
    "input": 2352,
    "output": 63,
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
    "output": 134,
    "cache_read": 0,
    "cache_create": 0
  },
  {
    "input": 12809,
    "output": 71,
    "cache_read": 0,
    "cache_create": 0
  },
  {
    "input": 12907,
    "output": 76,
    "cache_read": 0,
    "cache_create": 0
  },
  {
    "input": 13005,
    "output": 79,
    "cache_read": 0,
    "cache_create": 0
  },
  {
    "input": 13106,
    "output": 76,
    "cache_read": 0,
    "cache_create": 0
  }
]
```
