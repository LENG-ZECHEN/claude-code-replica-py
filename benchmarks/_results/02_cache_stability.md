# Benchmark 2 — Prompt-Cache Prefix Stability

Generated: 2026-05-25T06:44:18.167875+00:00

## Scenario

For each round (5 total), the same `tool_use_id` (tu_cache_stab_001)
is processed with **drifting content** (60 KB body + a per-round
timestamp suffix). We hash either (a) the returned pointer string
or (b) the full built context (system + messages) and count how
many distinct hashes appear across the 5 rebuilds.

Two configurations:
- **Stable**: real `ContentReplacementState` (production default)
- **Naive**: `ContentReplacementState` replaced with a no-op
  (`_NoCache`) — simulates the naive implementation that
  re-externalizes on every rebuild.

## Pointer-level results

| Mode | Rounds | Unique hashes | All identical? | Stability score |
| ---- | ------ | ------------- | -------------- | --------------- |
| stable | 5 | 1 | True | **5/5** |
| naive  | 5 | 5 | False | **1/5** |

## Full-context results (system + messages SHA-256)

| Mode | Rounds | Unique hashes | All identical? | Stability score |
| ---- | ------ | ------------- | -------------- | --------------- |
| stable | 5 | 1 | True | **5/5** |
| naive  | 5 | 5 | False | **1/5** |

## Verdict

The stable implementation produces **5/5** identical pointers and **5/5** identical full-context prefixes, while the naive implementation produces **1/5** / **1/5** respectively. Prompt-cache prefix bytes only match when hashes are identical, so this is a direct measure of cache hit rate under content drift.
