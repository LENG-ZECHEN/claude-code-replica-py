#!/usr/bin/env bash
# scripts/run_next.sh — prepare and (optionally) launch the next milestone session.
#
# Usage:
#   ./scripts/run_next.sh              show pre-flight + next prompt (default)
#   ./scripts/run_next.sh --run        ... and pipe the prompt to `claude --print`
#   ./scripts/run_next.sh --copy       ... and copy the prompt to the macOS clipboard
#
# Pre-flight verifies:
#   - HANDOFF.md exists at project root
#   - working tree is clean (no uncommitted changes)
#   - pytest is green at the current HEAD
#
# Exits non-zero on pre-flight failure.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

HANDOFF="$PROJECT_ROOT/HANDOFF.md"
MODE="${1:-show}"

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

printf '=== Project: %s ===\n\n' "$PROJECT_ROOT"

if [ ! -f "$HANDOFF" ]; then
  printf 'ERROR: HANDOFF.md not found at %s\n' "$HANDOFF"
  printf '       The previous milestone session should have generated it\n'
  printf '       using templates/handoff_template.md.\n'
  exit 1
fi
printf 'OK   HANDOFF.md present\n'

if ! git diff --quiet HEAD 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
  printf 'ERROR: working tree has uncommitted changes:\n'
  git status --short
  printf '\n       Commit or stash before starting the next milestone.\n'
  exit 1
fi
printf 'OK   working tree clean\n\n'

printf '=== Latest commit ===\n'
git log -1 --pretty=format:'  %h %s%n  (%ar by %an)%n'
printf '\n'

printf '=== Pytest baseline ===\n'
if pytest --tb=no -q 2>&1 | tail -3; then
  printf 'OK   pytest passed\n'
else
  printf 'WARN pytest output above — verify before proceeding\n'
fi

# ---------------------------------------------------------------------------
# Extract Section 5 prompt
# ---------------------------------------------------------------------------

NEXT_PROMPT=$(awk '
  /^## 5\./        { in_section = 1; next }
  in_section && /^## /    { in_section = 0 }
  in_section && /^```/    { in_block = 1 - in_block; next }
  in_section && in_block  { print }
' "$HANDOFF")

if [ -z "$NEXT_PROMPT" ]; then
  printf '\nERROR: Could not extract prompt from HANDOFF.md Section 5\n'
  printf '       Make sure Section 5 contains a fenced code block.\n'
  exit 1
fi

printf '\n=== Next session prompt (from HANDOFF.md Section 5) ===\n\n'
printf '%s\n' "$NEXT_PROMPT"

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

printf '\n=== Next steps ===\n'
case "$MODE" in
  --run)
    printf 'Launching: claude --print (log -> logs/)\n'
    mkdir -p logs
    TS=$(date +%Y%m%d-%H%M%S)
    LOG="logs/run-${TS}.log"
    printf '%s\n' "$NEXT_PROMPT" | claude --print 2>&1 | tee "$LOG"
    printf '\nLog written to: %s\n' "$LOG"
    ;;
  --copy)
    if command -v pbcopy >/dev/null 2>&1; then
      printf '%s\n' "$NEXT_PROMPT" | pbcopy
      printf 'Prompt copied to clipboard. Open a fresh claude session and paste.\n'
    else
      printf 'pbcopy not found (this flag is macOS-only).\n'
      exit 1
    fi
    ;;
  show|*)
    printf '1. Open a new Claude Code session: cd %s && claude\n' "$PROJECT_ROOT"
    printf '2. Paste the prompt above.\n\n'
    printf 'Shortcuts:\n'
    printf '  ./scripts/run_next.sh --copy   copy prompt to clipboard (macOS)\n'
    printf '  ./scripts/run_next.sh --run    invoke claude --print autonomously\n'
    ;;
esac
