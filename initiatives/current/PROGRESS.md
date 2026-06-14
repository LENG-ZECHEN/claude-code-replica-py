# session-memory-dream progress log

Cumulative milestone log for the `session-memory-dream` initiative.
One block per milestone, newest at the bottom. **Append only —
machine-enforced.** `run_all_milestones.sh` exit-gate check 6 walks
`baseline_commit..HEAD`, finds every prior `[sm-dream/M{i}]` commit,
and verifies the corresponding `## M{i} — done YYYY-MM-DD` block still
exists in this file. Deleting or rewriting a prior block halts the loop.

Each milestone agent APPENDS one block at exit ritual, formatted:

```
## M{N} — done YYYY-MM-DD

- **commit**: `(see git log)` `[sm-dream/M{N}] <subject>`
- **tests**: <before> → <after> (+N)
- **mypy**: clean | **ruff**: clean
- **files changed**: `<file1>`, `<file2>`, ...
- **exit gate**: `<gate text from §2>` → PASS (<one-line evidence>)
- **notes**: <optional, ≤1 line>
```

<!-- Milestone blocks begin below. The first real milestone (M1) appends
     its block here; do not place any entry above this line. -->

## M1 — done 2026-06-15

- **commit**: `(see git log)` `[sm-dream/M1] extract ForkedAgentRunner from ExtractMemoriesRunner`
- **tests**: 912 → 923 (+11)
- **mypy**: clean | **ruff**: clean
- **files changed**: `src/simple_coding_agent/forked_agent.py`, `src/simple_coding_agent/extract_memories.py`, `tests/test_forked_agent.py`
- **exit gate**: `test_forked_agent.py passes (≥ 6 cases) AND existing test_extract_memories*.py stay green` → PASS (35 passed in targeted run; 923 total, +11 from 912)
- **notes**: Narrowed bare `except Exception: pass` in _build_whitelist_tools to `UnknownToolError` only; context injection bug fixed (base_messages now sent as context_messages)
