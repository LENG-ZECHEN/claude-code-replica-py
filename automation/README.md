# automation/ — setup and runner reference

> Operating guide for the initiative automation harness in this repo.
> For the actual workflow (Phase 1 bootstrap, Phase 2 execute + review),
> see [`RUNBOOK.md`](./RUNBOOK.md). This README covers one-time setup
> and what the scripts here do.

## What lives here

```
automation/
├── README.md             # this file — one-time setup + runner reference
├── RUNBOOK.md            # the actual workflow (Phase 1 / Phase 2)
├── INBOX.md              # where you write the next initiative brief
├── scripts/
│   ├── run_all_milestones.sh   # Phase 2 entry point — full loop + review
│   └── run_next.sh             # single-milestone debug runner
├── templates/            # 8 skeletons used by Phase 1 + 2
└── logs/                 # gitignored scratch; per-initiative logs live
                          #   under initiatives/current/logs/
```

## One-time setup

### 1. Claude Code CLI

Both scripts call `claude --print --model claude-opus-4-8`. You need:

- Claude Code CLI v2.1.51 or later (`claude --version`)
- A claude.ai account on Pro / Max / Team / Enterprise plan
- The model `claude-opus-4-8` accessible to your account

### 2. allowedTools / disallowedTools

`claude --print` **silently ignores** `~/.claude/settings.json`
permissions and hangs when it wants to use an unapproved tool. The
scripts in this folder pass the permission whitelist as CLI flags
(`--allowedTools` / `--disallowedTools`) on every invocation, so you do
**NOT** need to configure `settings.json` for the automation to work.

The whitelist is hard-coded near the top of both `run_all_milestones.sh`
and `run_next.sh` — they share the exact same list:

| Category | Why included |
|---|---|
| `Read` / `Write` / `Edit` | TDD: write tests, implement, refactor |
| `Glob` / `Grep` | Cross-file searches |
| `Task*` | Milestone progress tracking |
| `Bash(git *)` | commits, log, diff, status |
| `Bash(pytest *)` / `Bash(mypy *)` / `Bash(ruff *)` / `Bash(python *)` | Quality gates |
| `Bash(pip *)` | Editable install or new test deps |
| `Bash(ls/cat/head/tail/grep/find/wc/diff *)` | File inspection |
| `Bash(mkdir/chmod/touch *)` | Scaffolding |
| **Denied** | `rm` / `rmdir` / `curl` / `wget` / `sudo` / `ssh` / `git push --force` |

The deny list is non-negotiable: these stop the worst non-recoverable
mistakes (mass delete, network exfil, force-push). If a future
initiative genuinely needs network access, edit the script explicitly —
do **not** blanket-allow.

### 3. Verify

```bash
cd /Users/leng/my-cc-py/python-replica
command -v claude
claude --version
./automation/scripts/run_all_milestones.sh --help
```

The first two commands verify Claude Code is installed and visible on
PATH. The final command prints the script's usage block without launching
pre-flight or any milestone sessions.

## Running

The full workflow lives in [`RUNBOOK.md`](./RUNBOOK.md). The TL;DR:

```bash
# 0. Write your brief in automation/INBOX.md (delete placeholder block).
$EDITOR automation/INBOX.md

# 1. Bootstrap (one prompt to a Claude session — Phase 1 in RUNBOOK).
#    Say to any Claude session:  "Run RUNBOOK Phase 1."
#    The session creates initiatives/current/ and generates per-milestone prompts.
#    It does NOT commit. You review and commit.

# 2. Review the bootstrap diff + commit.
cd python-replica
git status && git diff
git add automation/INBOX.md NOW.md initiatives/
git commit -m "[<commit_prefix>/bootstrap] ..."

# 3. Run the loop — one session per milestone + one review session.
./automation/scripts/run_all_milestones.sh
```

### Script flags — `run_all_milestones.sh`

```
./automation/scripts/run_all_milestones.sh                  run every milestone in config, skipping completed ones
./automation/scripts/run_all_milestones.sh M3 M4            run a subset, skipping completed ones (skips review)
./automation/scripts/run_all_milestones.sh --dry-run        print prompts only
./automation/scripts/run_all_milestones.sh --skip-review    run milestones, skip wrap-up session
./automation/scripts/run_all_milestones.sh --skip-quality   skip the pytest exit-gate check (faster, less safe)
./automation/scripts/run_all_milestones.sh --help           usage
```

### Script flags — `run_next.sh` (debug runner)

```
./automation/scripts/run_next.sh M3            show pre-flight + prompt path for M3
./automation/scripts/run_next.sh M3 --run      launch a single-milestone session for M3
./automation/scripts/run_next.sh --help        usage
```

`run_next.sh` is for when the main loop halts and you need to retry one
milestone. It does **NOT** enforce the 5-check exit gate — re-run the
full loop afterward. The full loop re-checks already-completed milestones,
skips the ones that still pass, and continues at the next incomplete
milestone.

### While the loop runs

- **Live view from another terminal**: `tail -f initiatives/current/logs/M*.log`
- **Review live log**: during wrap-up, `tail -f automation/logs/<archive-slug>-review.log`
  (the script copies the finalized log into the archive and amends the wrap commit).
- **Abort**: Ctrl-C in the terminal running the script. Prior commits are intact.
  Resume with `./automation/scripts/run_all_milestones.sh M{N} M{N+1} ...`
  for a narrow debug pass, or rerun `./automation/scripts/run_all_milestones.sh`
  with no milestone filter to skip completed milestones and trigger review.

## Failure modes

Most failure cases live in [`RUNBOOK.md`](./RUNBOOK.md) "Failure modes".
The quick reference here covers script-level issues only:

| Symptom | Likely cause | Action |
|---|---|---|
| Script halts: `config not found` | Phase 1 not run yet | Run Phase 1 first (see RUNBOOK) |
| Script halts: `M{N} failed exit-gate check N` | Milestone agent skipped a ritual step | Read which check name failed; inspect `initiatives/current/logs/M{N}.log` |
| Script halts: `review wrap-gate check N failed` | Review session missed part of archive / clean-tree ritual | Inspect `automation/logs/<archive-slug>-review.log` and any archived `initiatives/_archive/<slug>/logs/review.log` |
| `working tree dirty` pre-flight | Uncommitted changes | `git stash` or `git commit` before retry |
| Tool calls prompt for permission | You ran `claude` directly instead of the script | Use the script — it passes `--allowedTools` as CLI flags |

## Cost reality

Each milestone session runs ~25-45 minutes and costs roughly $15-30 at
Opus pricing. The final review session adds ~$5-15. A 5-milestone
initiative is roughly $80-160 total. Run a single `M1` first to
calibrate before chaining the rest.
