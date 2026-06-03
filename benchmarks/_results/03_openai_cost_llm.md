# Benchmark 3 — Real-API Token-Cost Comparison

Generated: 2026-05-25T08:34:56.734009+00:00
Model: `qwen-plus-latest`  ·  Prices (USD per 1M tokens): in=$0.11, out=$0.28 (`model-table`)

## Scenario

- Seeded transcript: **8** tool exchanges × 6,000 chars each
- Driven turns:      **5**
- Full pipeline:     compactor ON + tool-result-store ON + microcompact ON, budget=8,000 tokens
- Naive baseline:    compactor OFF + tool-result-store OFF + microcompact OFF, budget=200,000 tokens

## Token & cost totals

| Variant | Calls | Input tokens | Output tokens | Total USD |
| ------- | ----- | ------------ | ------------- | --------- |
| full    | 6 | 19,153 | 855 | $0.002346 |
| naive   | 5 | 64,645 | 494 | $0.007249 |

## Savings

- Input tokens saved:  **45,492** (70.37%)
- Output tokens saved: **-361** (-73.08%)
- USD saved:           **$0.004903** (67.64%)

## Per-call token traces

### full

```json
[
  {
    "input": 7658,
    "output": 435,
    "cache_read": 0,
    "cache_create": 0
  },
  {
    "input": 2055,
    "output": 130,
    "cache_read": 0,
    "cache_create": 0
  },
  {
    "input": 2214,
    "output": 72,
    "cache_read": 0,
    "cache_create": 0
  },
  {
    "input": 2313,
    "output": 67,
    "cache_read": 0,
    "cache_create": 0
  },
  {
    "input": 2402,
    "output": 87,
    "cache_read": 0,
    "cache_create": 0
  },
  {
    "input": 2511,
    "output": 64,
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
    "output": 159,
    "cache_read": 0,
    "cache_create": 0
  },
  {
    "input": 12834,
    "output": 89,
    "cache_read": 0,
    "cache_create": 0
  },
  {
    "input": 12950,
    "output": 85,
    "cache_read": 0,
    "cache_create": 0
  },
  {
    "input": 13057,
    "output": 79,
    "cache_read": 0,
    "cache_create": 0
  },
  {
    "input": 13158,
    "output": 82,
    "cache_read": 0,
    "cache_create": 0
  }
]
```
