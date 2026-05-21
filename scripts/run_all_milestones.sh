#!/usr/bin/env bash
# scripts/run_all_milestones.sh
#
# Autonomous milestone runner — loops over selected milestones, each in a
# fresh `claude --print` process (independent context). Spawns claude with
# cwd = /Users/leng/my-cc-py so the session can see both python-replica/
# and claude-code-source-code/. Uses --remote-control so you can watch /
# co-pilot from the Claude mobile app or claude.ai/code, and --model
# claude-opus-4-7 to pin the model.
#
# Requirements:
#   - Claude Code CLI v2.1.51+ (you have 2.1.146, OK)
#   - claude.ai account on Pro / Max / Team / Enterprise plan
#   - ~/.claude/settings.json with the recommended permissions whitelist
#     (run `./scripts/run_all_milestones.sh --print-allowlist` to see it)
#   - python-replica/templates/milestone_prompt_template.md present
#   - Working tree clean before launch (checked in python-replica/.git)
#
# Usage:
#   ./scripts/run_all_milestones.sh                       # M2..M5 (default)
#   ./scripts/run_all_milestones.sh M3 M4                 # custom subset
#   ./scripts/run_all_milestones.sh --dry-run             # print prompts only
#   ./scripts/run_all_milestones.sh --print-allowlist     # show settings JSON
#   ./scripts/run_all_milestones.sh --help                # this header
#
# What you do while it's running:
#   1. Open Claude mobile app (or claude.ai/code in any browser)
#   2. Each milestone's session appears as it spawns
#   3. Watch, intervene, or let it run unattended
#   4. Tail logs in parallel:  tail -f python-replica/logs/M*.log

set -euo pipefail

# Resolve script dir, then jump UP TWO levels (scripts/ -> python-replica/ -> my-cc-py/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"   # /Users/leng/my-cc-py
cd "$PROJECT_ROOT"

REPLICA_DIR="python-replica"
TEMPLATE="$REPLICA_DIR/templates/milestone_prompt_template.md"
LOGS_DIR="$REPLICA_DIR/logs"
CLAUDE_MODEL="claude-opus-4-7"

# ---------------------------------------------------------------------------
# Lookups (from RUNTIME_ACTIVATION_PLAN.md sections 2 + 4)
# ---------------------------------------------------------------------------

phase_ids_for() {
  case "$1" in
    M1) echo "A1, A3, A4, B1" ;;
    M2) echo "C1, C2" ;;
    M3) echo "C3, C4, B3" ;;
    M4) echo "D1, D2, D3" ;;
    M5) echo "A2, B4" ;;
    *)  echo "(unknown)" ;;
  esac
}

section_ids_for() {
  case "$1" in
    M1) echo "3.1 + 3.2" ;;
    M2) echo "3.3 (stress + microcompact)" ;;
    M3) echo "3.3 (metrics) + 3.2 (session-persist)" ;;
    M4) echo "3.4 + 3.5 scenarios 1,2" ;;
    M5) echo "3.5 scenario 3" ;;
    *)  echo "(unknown)" ;;
  esac
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

print_allowlist() {
  cat <<'EOF'
Add this block to ~/.claude/settings.json (merge with existing keys):

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

Then restart any open Claude Code session for the new permissions to load.
EOF
}

show_help() {
  sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
}

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------

DRY_RUN=0
MILESTONES=()

for arg in "$@"; do
  case "$arg" in
    --help|-h)         show_help; exit 0 ;;
    --print-allowlist) print_allowlist; exit 0 ;;
    --dry-run)         DRY_RUN=1 ;;
    M[1-9])            MILESTONES+=("$arg") ;;
    M[1-9][0-9])       MILESTONES+=("$arg") ;;
    *)                 echo "Unknown arg: $arg"; echo "Try --help"; exit 2 ;;
  esac
done

if [ ${#MILESTONES[@]} -eq 0 ]; then
  MILESTONES=(M2 M3 M4 M5)
fi

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

printf '=== Pre-flight ===\n'
printf 'cwd        : %s (sessions will spawn here)\n' "$PROJECT_ROOT"
printf 'project    : %s\n' "$REPLICA_DIR"

if [ ! -f "$TEMPLATE" ]; then
  echo "ERROR: template not found: $TEMPLATE"
  exit 1
fi
echo "OK   template present: $TEMPLATE"

if ! command -v claude >/dev/null 2>&1; then
  echo "ERROR: 'claude' CLI not found on PATH"
  exit 1
fi
echo "OK   claude CLI: $(claude --version 2>&1 | head -1)"
echo "     model     : $CLAUDE_MODEL"

if [ "$DRY_RUN" -eq 0 ]; then
  if ! git -C "$REPLICA_DIR" diff --quiet HEAD 2>/dev/null \
     || ! git -C "$REPLICA_DIR" diff --cached --quiet 2>/dev/null; then
    echo "ERROR: working tree in $REPLICA_DIR is dirty. Commit or stash before launching."
    git -C "$REPLICA_DIR" status --short
    exit 1
  fi
  echo "OK   working tree clean (in $REPLICA_DIR)"

  if ! grep -q 'Bash(pytest' "$HOME/.claude/settings.json" 2>/dev/null; then
    echo
    echo "WARN: ~/.claude/settings.json does not appear to have the recommended"
    echo "      permissions whitelist. Each tool call may prompt you, which"
    echo "      defeats the autonomous run. Run:"
    echo "        ./scripts/run_all_milestones.sh --print-allowlist"
    echo "      to see what to add. Press Ctrl-C to abort, or Enter to continue."
    read -r _
  fi
fi

mkdir -p "$LOGS_DIR"

printf '\n=== Plan ===\n'
printf 'Milestones : %s\n' "${MILESTONES[*]}"
printf 'Logs       : %s/\n' "$LOGS_DIR"
printf 'Template   : %s\n' "$TEMPLATE"
printf 'Dry-run    : %s\n\n' "$DRY_RUN"

# ---------------------------------------------------------------------------
# Loop
# ---------------------------------------------------------------------------

for M in "${MILESTONES[@]}"; do
  printf '================================================================\n'
  printf '=== Starting %s at %s ===\n' "$M" "$(date)"
  printf '================================================================\n'

  PHASE_IDS=$(phase_ids_for "$M")
  SECTION_IDS=$(section_ids_for "$M")

  PROMPT_FILE=$(mktemp -t "prompt-${M}-XXXX")
  sed \
    -e "s/{{MILESTONE}}/$M/g" \
    -e "s|{{PHASE_IDS}}|$PHASE_IDS|g" \
    -e "s|{{SECTION_IDS}}|$SECTION_IDS|g" \
    "$TEMPLATE" > "$PROMPT_FILE"

  if [ "$DRY_RUN" -eq 1 ]; then
    printf -- '--- prompt for %s ---\n' "$M"
    cat "$PROMPT_FILE"
    printf -- '--- end ---\n\n'
    rm -f "$PROMPT_FILE"
    continue
  fi

  LOG="$LOGS_DIR/${M}.log"
  printf 'Log         : %s\n' "$LOG"
  printf 'Live view   : tail -f %s   (run in another terminal)\n' "$LOG"
  printf 'Model       : %s\n\n' "$CLAUDE_MODEL"

  # Launch a fresh claude session with cwd = $PROJECT_ROOT (we're already there).
  # NOTE: --remote-control was removed — it is incompatible with --print mode
  # (--print is headless, --remote-control needs an auth/browser handshake).
  # For live observation, use `tail -f` on the log file in another terminal.
  # --model pins to Opus 4.7 (uses your account plan tier, e.g. Max).
  if ! claude --print --model "$CLAUDE_MODEL" \
       < "$PROMPT_FILE" 2>&1 | tee "$LOG"; then
    echo
    echo "ERROR: $M's claude invocation exited non-zero. See $LOG."
    rm -f "$PROMPT_FILE"
    exit 1
  fi

  rm -f "$PROMPT_FILE"

  # Exit-gate: did the milestone actually commit?
  if ! git -C "$REPLICA_DIR" log --oneline -1 | grep -q "P9-${M}"; then
    echo
    echo "ERROR: $M did not produce a 'P9-${M}' commit. Loop stopping."
    echo "Latest commits in $REPLICA_DIR:"
    git -C "$REPLICA_DIR" log --oneline -5
    exit 1
  fi

  printf '\n=== %s done at %s ===\n\n' "$M" "$(date)"
done

printf '================================================================\n'
printf '=== All milestones complete ===\n'
printf '================================================================\n'
git -C "$REPLICA_DIR" log --oneline -10
