# AUTONOMOUS_RUN_SETUP

One-time setup before running `scripts/run_all_milestones.sh`.

---

## 1. Verify Claude Code version (need >= 2.1.51 for `--remote-control`)

```bash
claude --version
# Expected: 2.1.51 or higher. You are on 2.1.146 — OK.
```

## 2. Verify Claude account plan

`--remote-control` requires a **Pro / Max / Team / Enterprise** plan on
claude.ai. Free-tier API keys alone are not enough. Confirm by visiting
claude.ai/account.

## 3. Install the allowedTools whitelist

Open `~/.claude/settings.json` and add the `permissions` block below.
**Merge** with your existing keys (do not delete `enabledPlugins`,
`theme`, etc.).

```json
{
  "permissions": {
    "allow": [
      "Read", "Write", "Edit",
      "Glob", "Grep",
      "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "TaskOutput",
      "Bash(git:*)",
      "Bash(pytest*)", "Bash(python:*)", "Bash(python3:*)",
      "Bash(mypy:*)", "Bash(ruff:*)", "Bash(pip:*)",
      "Bash(ls:*)", "Bash(ls)", "Bash(pwd)", "Bash(cd:*)",
      "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)",
      "Bash(grep:*)", "Bash(find:*)", "Bash(wc:*)", "Bash(diff:*)",
      "Bash(mkdir:*)", "Bash(chmod:*)", "Bash(touch:*)",
      "Bash(echo:*)", "Bash(printf:*)"
    ],
    "deny": [
      "Bash(rm:*)", "Bash(rmdir:*)",
      "Bash(curl:*)", "Bash(wget:*)",
      "Bash(sudo:*)", "Bash(ssh:*)", "Bash(scp:*)",
      "Bash(npm publish:*)", "Bash(git push --force:*)"
    ]
  }
}
```

### Why this set

| Category | Why included |
|---|---|
| `Read` / `Write` / `Edit` | TDD: write tests, implement, refactor |
| `Glob` / `Grep` | Cross-file searches the model relies on |
| `Task*` | Milestone task tracking |
| `Bash(git:*)` | commits, log, diff, status |
| `Bash(pytest* / mypy:* / ruff:* / python*)` | Quality gates |
| `Bash(pip:*)` | Editable install or new test deps |
| `Bash(ls/cat/head/tail/grep/find/wc/diff)` | File inspection |
| `Bash(mkdir/chmod/touch)` | Scaffolding |
| **Denied: rm / curl / wget / sudo / ssh / force-push** | Eliminates the worst non-recoverable mistakes |

The denylist is non-negotiable. Even with `permissions.allow`, anything in
`deny` will block. If a future milestone genuinely needs network access,
edit this file explicitly — never blanket-allow.

## 4. Restart any open Claude Code session

Permissions are loaded at session start. After editing
`~/.claude/settings.json`, kill and restart any open `claude` window for
the new rules to take effect.

## 5. Pre-flight test

```bash
cd /Users/leng/my-cc-py/python-replica

# Inspect what each milestone's prompt will look like:
./scripts/run_all_milestones.sh --dry-run M2

# When happy, launch the real run (M2 -> M3 -> M4 -> M5):
./scripts/run_all_milestones.sh
```

## 6. While it runs

- **Watch from mobile**: open Claude iOS/Android app. Each milestone
  spawns its own session — you'll see them appear as the loop advances.
- **Watch from desktop**: open claude.ai/code in any browser, log in;
  the running session appears in the sidebar.
- **Watch from another terminal**: `tail -f logs/M*.log`
- **Intervene**: type into the remote-controlled session at any point.
  The local `claude --print` process reflects your input.
- **Abort**: Ctrl-C in the terminal running the loop kills the current
  milestone but leaves prior commits intact. Restart with
  `./scripts/run_all_milestones.sh M3 M4 M5` to resume from where it
  stopped.

## 7. Failure modes

| Symptom | Cause | Action |
|---|---|---|
| Loop stops with "did not produce a P9-MN commit" | Milestone session exited without committing | Check `logs/MN.log` for why; commit manually if work is salvageable, then resume |
| Each tool call still prompts | Whitelist not loaded | Restart the claude session; re-check `~/.claude/settings.json` JSON validity |
| Remote control not appearing on phone | Plan tier insufficient, or `--remote-control` flag rejected | Check plan; check `claude --remote-control --help` |
| `working tree dirty` pre-flight error | Uncommitted changes from manual edits | `git stash` or `git commit` before re-launching |

## 8. Cost reality check

Each milestone session runs ~1-3 hours and processes thousands of tokens
per turn. Expect **$10-30 per milestone** at Opus pricing. The 4-milestone
loop (M2-M5) total: **roughly $40-120**.

Before launching the full loop, run M2 alone first, observe actual cost,
then decide whether to chain the rest:

```bash
./scripts/run_all_milestones.sh M2
# inspect cost via Claude usage dashboard, then:
./scripts/run_all_milestones.sh M3 M4 M5
```
