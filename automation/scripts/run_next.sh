#!/usr/bin/env bash
# automation/scripts/run_next.sh
#
# Single-milestone debug runner. Re-launches ONE milestone session
# without running the full loop or the final review. Use this when
# run_all_milestones.sh halted at M{N} and you want to retry that
# specific milestone after fixing whatever caused the halt.
#
# This is the recovery path documented in RUNBOOK Failure modes.
#
# Usage:
#   ./automation/scripts/run_next.sh M3            show pre-flight + prompt path
#   ./automation/scripts/run_next.sh M3 --run      pre-flight + invoke claude --print
#   ./automation/scripts/run_next.sh --help        this header
#
# Pre-flight matches run_all_milestones.sh:
#   - initiatives/current/config.yaml exists
#   - initiatives/current/prompts/M{N}.md exists
#   - claude CLI on PATH
#   - working tree in python-replica/ is clean
#
# IMPORTANT: this script does NOT enforce the 6-check exit gate that
# run_all_milestones.sh enforces (1: commit subject / 2: HANDOFF.md modified
# in commit / 3: PROGRESS.md entry exists / 4: pytest green / 5: HANDOFF
# 5-section structure / 6: PROGRESS.md and HANDOFF.md preserve all prior
# milestone blocks since baseline — append-only contract). It is strictly
# a debug runner. After verifying the milestone manually, re-run
# `./automation/scripts/run_all_milestones.sh` to continue the loop —
# the 6-check gate there will skip already-good milestones and pick up
# from the next undone one.

set -euo pipefail

# ---------------------------------------------------------------------------
# Paths (matches run_all_milestones.sh layout — script lives 2 dirs deep)
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPLICA_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"        # python-replica/
PROJECT_ROOT="$(cd "$REPLICA_DIR/.." && pwd)"         # /Users/leng/my-cc-py

CURRENT_DIR="$REPLICA_DIR/initiatives/current"
CONFIG="$CURRENT_DIR/config.yaml"
PROMPTS_DIR="$CURRENT_DIR/prompts"
LOGS_DIR="$CURRENT_DIR/logs"

CLAUDE_MODEL="claude-opus-4-7"

# ---------------------------------------------------------------------------
# Permission whitelist — IDENTICAL to run_all_milestones.sh.
# claude --print silently ignores ~/.claude/settings.json, so these
# CLI flags are MANDATORY (without them claude --print hangs when a
# tool needs permission).
# ---------------------------------------------------------------------------

ALLOWED_TOOLS="Read Write Edit Glob Grep \
TaskCreate TaskUpdate TaskList TaskGet TaskOutput \
Bash(git *) Bash(pytest *) Bash(python *) Bash(python3 *) \
Bash(mypy *) Bash(ruff *) Bash(pip *) \
Bash(ls *) Bash(ls) Bash(pwd) Bash(cd *) \
Bash(cat *) Bash(head *) Bash(tail *) \
Bash(grep *) Bash(find *) Bash(wc *) Bash(diff *) \
Bash(mkdir *) Bash(chmod *) Bash(touch *) \
Bash(echo *) Bash(printf *)"

DISALLOWED_TOOLS="Bash(rm *) Bash(rmdir *) \
Bash(curl *) Bash(wget *) \
Bash(sudo *) Bash(ssh *) Bash(scp *) \
Bash(npm publish *) Bash(git push --force *)"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

die() { echo "ERROR: $*" >&2; exit 1; }

show_help() {
  sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
}

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------

MILESTONE=""
RUN=0

for arg in "$@"; do
  case "$arg" in
    --help|-h)       show_help; exit 0 ;;
    --run)           RUN=1 ;;
    M[0-9])          MILESTONE="$arg" ;;
    M[0-9][0-9])     MILESTONE="$arg" ;;
    *)               die "Unknown arg: $arg (expected 'M{N}' or '--run'; try --help)" ;;
  esac
done

[ -n "$MILESTONE" ] || die "milestone ID required, e.g. './run_next.sh M3' (try --help)"

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

cd "$PROJECT_ROOT"

PROMPT="$PROMPTS_DIR/${MILESTONE}.md"

[ -f "$CONFIG" ]    || die "config not found: $CONFIG (run Phase 1 first)"
[ -f "$PROMPT" ]    || die "prompt missing for $MILESTONE: $PROMPT"
command -v claude >/dev/null 2>&1 || die "claude CLI not on PATH"

if [ -n "$(git -C "$REPLICA_DIR" status --porcelain)" ]; then
  git -C "$REPLICA_DIR" status --short
  die "working tree in $REPLICA_DIR is dirty — commit, stash, or remove untracked files, then retry (untracked files are NOT exempt: a half-bootstrapped initiatives/current/ or a crashed milestone agent leaving new test files would silently pollute Phase 2; see RUNBOOK Pre-flight)"
fi

printf '=== Pre-flight ===\n'
printf 'milestone : %s\n' "$MILESTONE"
printf 'prompt    : %s\n' "$PROMPT"
printf 'config    : %s\n' "$CONFIG"
printf 'model     : %s\n' "$CLAUDE_MODEL"
printf 'last 3 commits:\n'
git -C "$REPLICA_DIR" log --oneline -3 | sed 's/^/  /'

if [ "$RUN" -eq 0 ]; then
  printf '\n=== Next steps ===\n'
  printf '1. Inspect the prompt: less %s\n' "$PROMPT"
  printf '2. To actually run:     %s %s --run\n' "$0" "$MILESTONE"
  exit 0
fi

# ---------------------------------------------------------------------------
# Run single milestone
# ---------------------------------------------------------------------------

mkdir -p "$LOGS_DIR"
LOG="$LOGS_DIR/${MILESTONE}.log"

printf '\n=== Launching %s at %s ===\n' "$MILESTONE" "$(date)"
printf 'Log: %s\n' "$LOG"
printf 'Live view: tail -f %s\n\n' "$LOG"

if ! claude --print --model "$CLAUDE_MODEL" \
     --allowedTools "$ALLOWED_TOOLS" \
     --disallowedTools "$DISALLOWED_TOOLS" \
     < "$PROMPT" 2>&1 | tee "$LOG"; then
  die "$MILESTONE: claude invocation exited non-zero (see $LOG)"
fi

printf '\n=== %s session ended at %s ===\n' "$MILESTONE" "$(date)"
printf 'NOTE: run_next.sh does NOT enforce the 6-check exit gate.\n'
printf '      Verify the milestone manually (commit / HANDOFF / PROGRESS /\n'
printf '      pytest / HANDOFF structure / append-only contract), then re-run\n'
printf '      ./automation/scripts/run_all_milestones.sh\n'
printf '      to continue the full loop.\n'
