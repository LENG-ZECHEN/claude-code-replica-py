#!/usr/bin/env bash
# automation/scripts/run_all_milestones.sh
#
# Phase 2 of automation/RUNBOOK.md (Execute + Review + Wrap-up).
# Reads initiatives/current/config.yaml + initiatives/current/prompts/M*.md
# produced by Phase 1, runs each milestone in a fresh `claude --print`
# session, then spawns one final review session that audits + archives
# the initiative.
#
# Conventions:
#   - cwd at invocation can be anywhere under python-replica/ or
#     /Users/leng/my-cc-py; the script cd's to PROJECT_ROOT itself.
#   - All paths in messages below are relative to python-replica/.
#
# IMPORTANT: `claude --print` silently ignores ~/.claude/settings.json
# permissions; the --allowedTools / --disallowedTools CLI flags below
# are MANDATORY (without them claude --print hangs when a tool needs
# permission). See automation/README.md for the full explanation.
#
# Usage:
#   ./automation/scripts/run_all_milestones.sh          # run every milestone in config
#   ./automation/scripts/run_all_milestones.sh M3 M4    # run a subset (debug)
#   ./automation/scripts/run_all_milestones.sh --dry-run
#   ./automation/scripts/run_all_milestones.sh --skip-review
#   ./automation/scripts/run_all_milestones.sh --help

set -euo pipefail

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPLICA_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"        # python-replica/
PROJECT_ROOT="$(cd "$REPLICA_DIR/.." && pwd)"         # /Users/leng/my-cc-py

CURRENT_DIR="$REPLICA_DIR/initiatives/current"
CONFIG="$CURRENT_DIR/config.yaml"
PROMPTS_DIR="$CURRENT_DIR/prompts"
LOGS_DIR="$CURRENT_DIR/logs"
REVIEW_TEMPLATE="$REPLICA_DIR/automation/templates/review.md"

CLAUDE_MODEL="claude-opus-4-7"

# ---------------------------------------------------------------------------
# Permission whitelist (passed as CLI flags; settings.json is ignored
# by `claude --print`).
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

show_help() {
  sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

# Read a top-level scalar key from initiatives/current/config.yaml.
# Handles `key: value` (no nested keys, no quoting).
read_config_scalar() {
  local key="$1"
  awk -v k="^${key}:" '$0 ~ k { sub(/^[^:]+:[ \t]*/, ""); print; exit }' "$CONFIG"
}

# List milestone IDs by scanning prompts/M*.md (sorted naturally).
# Used only for pre-flight cross-check against config.yaml.
list_milestones_from_prompts() {
  local f
  for f in "$PROMPTS_DIR"/M*.md; do
    [ -f "$f" ] || continue
    basename "$f" .md
  done | sort -V
}

# List milestone IDs from initiatives/current/config.yaml in DECLARATION
# ORDER (this is what RUNBOOK Phase 2A specifies as the execution order).
# Matches keys shaped like "  M{digits}:" under the milestones: block.
list_milestones_from_config() {
  awk '/^  M[0-9]+:/ { sub(/^  /, ""); sub(/:.*$/, ""); print }' "$CONFIG"
}

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------

DRY_RUN=0
SKIP_REVIEW=0
SKIP_QUALITY=0
MILESTONE_FILTER=()

for arg in "$@"; do
  case "$arg" in
    --help|-h)       show_help; exit 0 ;;
    --dry-run)       DRY_RUN=1 ;;
    --skip-review)   SKIP_REVIEW=1 ;;
    --skip-quality)  SKIP_QUALITY=1 ;;
    M[0-9])          MILESTONE_FILTER+=("$arg") ;;
    M[0-9][0-9])     MILESTONE_FILTER+=("$arg") ;;
    *)               die "Unknown arg: $arg (try --help)" ;;
  esac
done

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

cd "$PROJECT_ROOT"

printf '=== Pre-flight ===\n'
printf 'cwd        : %s\n' "$PROJECT_ROOT"
printf 'project    : %s\n' "$(basename "$REPLICA_DIR")"

[ -f "$CONFIG" ]            || die "config not found: $CONFIG (run Phase 1 first)"
[ -d "$PROMPTS_DIR" ]       || die "prompts dir not found: $PROMPTS_DIR (run Phase 1 first)"
[ -f "$REVIEW_TEMPLATE" ]   || die "review template missing: $REVIEW_TEMPLATE"
command -v claude >/dev/null 2>&1 || die "claude CLI not on PATH"

INITIATIVE_SLUG=$(read_config_scalar "slug")
COMMIT_PREFIX=$(read_config_scalar "commit_prefix")
ARCHIVE_SLUG=$(read_config_scalar "archive_slug")

[ -n "$INITIATIVE_SLUG" ]   || die "slug missing from $CONFIG"
[ -n "$COMMIT_PREFIX" ]     || die "commit_prefix missing from $CONFIG"
[ -n "$ARCHIVE_SLUG" ]      || die "archive_slug missing from $CONFIG"

printf 'slug       : %s\n' "$INITIATIVE_SLUG"
printf 'prefix     : %s\n' "$COMMIT_PREFIX"
printf 'archive    : %s\n' "$ARCHIVE_SLUG"
printf 'model      : %s\n' "$CLAUDE_MODEL"

ALL_MILESTONES=()
while IFS= read -r m; do
  [ -n "$m" ] && ALL_MILESTONES+=("$m")
done < <(list_milestones_from_config)

[ ${#ALL_MILESTONES[@]} -gt 0 ] || die "no milestones found in $CONFIG (expected '  M{N}:' entries under 'milestones:')"

# Pre-flight cross-check: every M{N} in config.yaml must have a matching
# prompts/M{N}.md file, and vice versa. Catches Phase 1 partial-bootstrap
# state and INBOX/config drift before we waste a milestone session.
CONFIG_SET=$(list_milestones_from_config | sort | tr '\n' ' ')
PROMPT_SET=$(list_milestones_from_prompts | sort | tr '\n' ' ')
if [ "$CONFIG_SET" != "$PROMPT_SET" ]; then
  printf 'config.yaml milestones : %s\n' "$CONFIG_SET" >&2
  printf 'prompts/M*.md files    : %s\n' "$PROMPT_SET" >&2
  die "config.yaml milestones != prompts/M*.md files (Phase 1 may have failed mid-way; see RUNBOOK Failure modes)"
fi

if [ ${#MILESTONE_FILTER[@]} -gt 0 ]; then
  MILESTONES=("${MILESTONE_FILTER[@]}")
else
  MILESTONES=("${ALL_MILESTONES[@]}")
fi

printf 'milestones : %s\n' "${MILESTONES[*]}"

if [ "$DRY_RUN" -eq 0 ]; then
  if ! git -C "$REPLICA_DIR" diff --quiet HEAD 2>/dev/null \
     || ! git -C "$REPLICA_DIR" diff --cached --quiet 2>/dev/null; then
    git -C "$REPLICA_DIR" status --short
    die "working tree in $REPLICA_DIR is dirty (commit or stash, then retry)"
  fi
  printf 'OK         : working tree clean\n'
fi

mkdir -p "$LOGS_DIR"

# ---------------------------------------------------------------------------
# Execute milestones (Phase 2A)
# ---------------------------------------------------------------------------

for M in "${MILESTONES[@]}"; do
  PROMPT="$PROMPTS_DIR/$M.md"
  [ -f "$PROMPT" ] || die "prompt missing for $M: $PROMPT"

  printf '\n================================================================\n'
  printf '=== Starting %s at %s ===\n' "$M" "$(date)"
  printf '================================================================\n'

  if [ "$DRY_RUN" -eq 1 ]; then
    printf -- '--- prompt for %s (first 40 lines) ---\n' "$M"
    head -40 "$PROMPT"
    printf -- '--- end ---\n'
    continue
  fi

  LOG="$LOGS_DIR/${M}.log"
  printf 'Prompt     : %s\n' "$PROMPT"
  printf 'Log        : %s\n' "$LOG"
  printf 'Live view  : tail -f %s\n\n' "$LOG"

  if ! claude --print --model "$CLAUDE_MODEL" \
       --allowedTools "$ALLOWED_TOOLS" \
       --disallowedTools "$DISALLOWED_TOOLS" \
       < "$PROMPT" 2>&1 | tee "$LOG"; then
    die "$M: claude invocation exited non-zero (see $LOG)"
  fi

  # ------------------------------------------------------------------------
  # Exit-gate: 5 independent checks. ALL must pass or the loop halts.
  # See automation/RUNBOOK.md Phase 2A for the full spec.
  # ------------------------------------------------------------------------

  # Check 1: commit subject contains [<commit_prefix>/<M>]
  if ! git -C "$REPLICA_DIR" log --oneline -1 | grep -qF "[${COMMIT_PREFIX}/${M}]"; then
    git -C "$REPLICA_DIR" log --oneline -5
    die "$M failed exit-gate check 1: no '[${COMMIT_PREFIX}/${M}]' commit at HEAD"
  fi

  # Check 2: HANDOFF.md was modified in that commit (exit ritual step 4)
  if ! git -C "$REPLICA_DIR" log -1 --name-only --pretty=format: \
       | grep -qx "initiatives/current/HANDOFF.md"; then
    die "$M failed exit-gate check 2: initiatives/current/HANDOFF.md was not modified in the commit (exit ritual step 4 skipped)"
  fi

  # Check 3: PROGRESS.md contains a '## M{N} — done YYYY-MM-DD' block
  # (exit ritual step 3). Use anchored regex so e.g. M1 does NOT match
  # M10 / M11 / etc., and so a bare "M1" appearing in a notes line does
  # not satisfy the gate.
  if ! grep -qE "^## ${M} — done [0-9]{4}-[0-9]{2}-[0-9]{2}" \
       "$REPLICA_DIR/initiatives/current/PROGRESS.md" 2>/dev/null; then
    die "$M failed exit-gate check 3: no '## $M — done YYYY-MM-DD' block found in initiatives/current/PROGRESS.md (exit ritual step 3 skipped or format wrong)"
  fi

  # Check 4: pytest still green (unless --skip-quality). The agent already
  # runs pytest before commit per §4, but we trust-but-verify here so a
  # skipped or flaky agent run does not propagate to the next milestone.
  if [ "$SKIP_QUALITY" -eq 0 ]; then
    if ! PYTEST_OUT="$(cd "$REPLICA_DIR" && pytest --tb=no -q 2>&1)"; then
      echo "---- pytest output (last 20 lines) ----" >&2
      echo "$PYTEST_OUT" | tail -20 >&2
      echo "---- end pytest output ----" >&2
      die "$M failed exit-gate check 4: pytest is now red (rerun: cd python-replica && pytest)"
    fi
  fi

  # Check 5: HANDOFF.md has the 5-section structure (proves the agent
  # used automation/templates/handoff_milestone.md, not a free-form
  # HANDOFF). Each section header must be present verbatim.
  HANDOFF_PATH="$REPLICA_DIR/initiatives/current/HANDOFF.md"
  for section in "## 1. Current initiative" \
                 "## 2. Completed milestones" \
                 "## 3. Current repo state" \
                 "## 4. Important constraints" \
                 "## 5. Next milestone guidance"; do
    if ! grep -qF "$section" "$HANDOFF_PATH"; then
      die "$M failed exit-gate check 5: HANDOFF.md is missing section header '$section' (agent did not use automation/templates/handoff_milestone.md)"
    fi
  done

  printf '\n=== %s done at %s ===\n' "$M" "$(date)"
done

# ---------------------------------------------------------------------------
# Review + wrap-up (Phase 2B + 2C)
# ---------------------------------------------------------------------------

if [ "$DRY_RUN" -eq 1 ] || [ "$SKIP_REVIEW" -eq 1 ]; then
  printf '\n================================================================\n'
  printf '=== Skipping review (--dry-run or --skip-review) ===\n'
  printf '================================================================\n'
  exit 0
fi

if [ ${#MILESTONE_FILTER[@]} -gt 0 ]; then
  printf '\n================================================================\n'
  printf '=== Skipping review (subset run; not all milestones executed) ===\n'
  printf '================================================================\n'
  exit 0
fi

printf '\n================================================================\n'
printf '=== Phase 2B + 2C: review + wrap-up at %s ===\n' "$(date)"
printf '================================================================\n'

REVIEW_LOG="$LOGS_DIR/review.log"
REVIEW_PROMPT="$LOGS_DIR/review_prompt.md"

# Substitute initiative-specific tokens into the review template.
sed \
  -e "s|{{INITIATIVE_SLUG}}|$INITIATIVE_SLUG|g" \
  -e "s|{{COMMIT_PREFIX}}|$COMMIT_PREFIX|g" \
  -e "s|{{ARCHIVE_SLUG}}|$ARCHIVE_SLUG|g" \
  "$REVIEW_TEMPLATE" > "$REVIEW_PROMPT"

printf 'Review prompt : %s\n' "$REVIEW_PROMPT"
printf 'Review log    : %s\n\n' "$REVIEW_LOG"

if ! claude --print --model "$CLAUDE_MODEL" \
     --allowedTools "$ALLOWED_TOOLS" \
     --disallowedTools "$DISALLOWED_TOOLS" \
     < "$REVIEW_PROMPT" 2>&1 | tee "$REVIEW_LOG"; then
  die "review session exited non-zero (see $REVIEW_LOG)"
fi

# Exit gate for the review session: it must have committed
# [<prefix>/wrap] AND moved current/ into _archive/<archive_slug>/.
if ! git -C "$REPLICA_DIR" log --oneline -1 | grep -qF "[${COMMIT_PREFIX}/wrap]"; then
  git -C "$REPLICA_DIR" log --oneline -5
  die "review session did not produce a '[${COMMIT_PREFIX}/wrap]' commit"
fi

if [ ! -d "$REPLICA_DIR/initiatives/_archive/$ARCHIVE_SLUG" ]; then
  die "review session did not archive initiative to initiatives/_archive/$ARCHIVE_SLUG"
fi

printf '\n================================================================\n'
printf '=== Initiative %s complete at %s ===\n' "$INITIATIVE_SLUG" "$(date)"
printf '================================================================\n'
git -C "$REPLICA_DIR" log --oneline -10
printf '\nREVIEW.md : initiatives/_archive/%s/REVIEW.md\n' "$ARCHIVE_SLUG"
