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
#   ./automation/scripts/run_all_milestones.sh          # run every milestone in config (skips completed ones)
#   ./automation/scripts/run_all_milestones.sh M3 M4    # run a subset (debug; skips completed ones)
#   ./automation/scripts/run_all_milestones.sh --dry-run
#   ./automation/scripts/run_all_milestones.sh --skip-review
#   ./automation/scripts/run_all_milestones.sh --skip-quality
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
SCRATCH_LOGS_DIR="$REPLICA_DIR/automation/logs"
REVIEW_TEMPLATE="$REPLICA_DIR/automation/templates/review.md"

CLAUDE_MODEL="claude-opus-4-7"

# ---------------------------------------------------------------------------
# Notification config (ntfy.sh)
# ---------------------------------------------------------------------------
# Push notifications are ON by default (topic 'lengzechen' is hard-coded
# below). Override or silence per-run via the NTFY_TOPIC env var:
#   ./run_all_milestones.sh                          -> push to 'lengzechen'
#   NTFY_TOPIC= ./run_all_milestones.sh              -> silence this run
#   NTFY_TOPIC=other ./run_all_milestones.sh         -> push to 'other'
# The `-` (no colon) in ${NTFY_TOPIC-lengzechen} is deliberate: it lets an
# explicitly-empty env var (NTFY_TOPIC=) silence the run, while an unset
# var falls back to the default. NTFY_URL can be overridden if you
# self-host ntfy.
#
# Privacy note: ntfy.sh topics are public read+write. Anyone who guesses
# 'lengzechen' can subscribe to (read) AND publish (spam) this topic.
# If this repo becomes public or you start using the topic for sensitive
# content, switch to a harder-to-guess name (e.g., 'lzc-agent-<random>').
NTFY_URL="${NTFY_URL:-https://ntfy.sh}"
NTFY_TOPIC="${NTFY_TOPIC-lengzechen}"

# Mutable run context referenced by failure notifications so die() can show
# which stage / log / milestone was in flight when the failure happened.
RUN_STARTED_AT="$(date +%s)"
CURRENT_STAGE="pre-flight"
CURRENT_LOG=""
MILESTONE_STARTED_AT=""

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

# ---------------------------------------------------------------------------
# Notification helpers (used by die() and the 5 per-stage notify points).
# All helpers are total: they never fail under `set -euo pipefail`.
# ---------------------------------------------------------------------------

# Format an elapsed-seconds delta as Hh Mm Ss / Mm Ss / Ss.
duration_since() {
  local start="$1"
  local now elapsed
  now="$(date +%s)"
  elapsed=$((now - start))

  if [ "$elapsed" -ge 3600 ]; then
    printf '%dh %dm %ds' "$((elapsed / 3600))" "$(((elapsed % 3600) / 60))" "$((elapsed % 60))"
  elif [ "$elapsed" -ge 60 ]; then
    printf '%dm %ds' "$((elapsed / 60))" "$((elapsed % 60))"
  else
    printf '%ds' "$elapsed"
  fi
}

git_head_summary() {
  git -C "${REPLICA_DIR:-.}" log --oneline -1 2>/dev/null || printf 'unknown'
}

git_branch_name() {
  git -C "${REPLICA_DIR:-.}" branch --show-current 2>/dev/null || printf 'unknown'
}

git_dirty_summary() {
  local dirty
  dirty="$(git -C "${REPLICA_DIR:-.}" status --short 2>/dev/null | head -20 || true)"
  if [ -n "$dirty" ]; then
    printf '%s' "$dirty"
  else
    printf 'clean'
  fi
}

log_tail_summary() {
  local log_path="${1:-}"
  local lines="${2:-20}"

  if [ -n "$log_path" ] && [ -f "$log_path" ]; then
    tail -"$lines" "$log_path" 2>/dev/null || true
  else
    printf 'no log file yet'
  fi
}

# Send a notification via ntfy.sh.
# Silent no-op if NTFY_TOPIC is empty or curl is missing. curl failures
# (timeout, DNS, ntfy outage) are also swallowed so push problems never
# break the automation. --max-time 5 prevents push outages from hanging
# the loop.
notify() {
  local title="$1"
  local text="$2"
  local tags="${3:-robot}"
  local priority="${4:-default}"

  [ -n "${NTFY_TOPIC:-}" ] || return 0
  command -v curl >/dev/null 2>&1 || return 0

  curl -sS --max-time 5 \
    -H "Title: ${title}" \
    -H "Tags: ${tags}" \
    -H "Priority: ${priority}" \
    -H "Markdown: yes" \
    --data-binary "$text" \
    "${NTFY_URL}/${NTFY_TOPIC}" \
    >/dev/null 2>&1 || true
}

# Run-context block reused as the prefix of every notification body.
notify_run_context() {
  cat <<EOF
Project: $(basename "${REPLICA_DIR:-unknown}")
Initiative: ${INITIATIVE_SLUG:-unknown}
Prefix: ${COMMIT_PREFIX:-unknown}
Model: ${CLAUDE_MODEL:-unknown}
Branch: $(git_branch_name)
HEAD: $(git_head_summary)
Elapsed: $(duration_since "$RUN_STARTED_AT")
EOF
}

die() {
  local msg="$*"
  echo "ERROR: $msg" >&2

  notify "❌ Claude automation failed" \
"$(notify_run_context)

Stage: ${CURRENT_STAGE:-unknown}
Milestone: ${M:-none}
Error: ${msg}

Git status:
$(git_dirty_summary)

Log: ${CURRENT_LOG:-none}

Last log lines:
$(log_tail_summary "${CURRENT_LOG:-}" 25)

Time: $(date)" \
    "x,rotating_light" "high"

  exit 1
}

# Read a top-level scalar key from initiatives/current/config.yaml.
# Handles `key: value` (no nested keys, no quoting). Strips inline
# `# comment` and trailing whitespace so values like `slug: foo  # bar`
# yield `foo`, not `foo  # bar` (would otherwise poison every grep / sed
# downstream that uses INITIATIVE_SLUG / COMMIT_PREFIX / ARCHIVE_SLUG).
read_config_scalar() {
  local key="$1"
  awk -v k="^${key}:" '$0 ~ k {
    sub(/^[^:]+:[ \t]*/, "")   # drop "key: " prefix
    sub(/[ \t]*#.*$/, "")      # drop inline "# comment"
    sub(/[ \t]+$/, "")          # drop trailing whitespace
    print
    exit
  }' "$CONFIG"
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

find_milestone_commit() {
  local m="$1"
  # Scan only THIS initiative's commit range (baseline_commit..HEAD).
  # Without the range restriction, a prior archived initiative that
  # happened to choose the same commit_prefix would poison the
  # resumability check — leading to either a false skip (rare; needs
  # the current PROGRESS.md to also contain that M{N} block) or a
  # misleading "PROGRESS block missing" failure (common, because the
  # current PROGRESS.md is fresh and has no M{N} block yet).
  # BASELINE_COMMIT is read from config.yaml during pre-flight and is
  # verified to be an ancestor of HEAD; if either step failed the
  # script has already die'd before find_milestone_commit is called.
  git -C "$REPLICA_DIR" log "${BASELINE_COMMIT}..HEAD" --format='%H%x09%s' \
    | awk -F '\t' -v marker="[${COMMIT_PREFIX}/${m}]" '
        index($2, marker) { print $1; exit }
      '
}

check_handoff_structure() {
  local handoff_path="$REPLICA_DIR/initiatives/current/HANDOFF.md"
  local section

  for section in "## 1. Current initiative" \
                 "## 2. Completed milestones" \
                 "## 3. Current repo state" \
                 "## 4. Important constraints" \
                 "## 5. Next milestone guidance"; do
    if ! grep -qF "$section" "$handoff_path"; then
      die "$1 failed exit-gate check 5: HANDOFF.md is missing section header '$section' (agent did not use automation/templates/handoff_milestone.md)"
    fi
  done
}

check_pytest_green() {
  local m="$1"

  if [ "$SKIP_QUALITY" -eq 0 ]; then
    if ! PYTEST_OUT="$(cd "$REPLICA_DIR" && pytest --tb=no -q 2>&1)"; then
      echo "---- pytest output (last 20 lines) ----" >&2
      echo "$PYTEST_OUT" | tail -20 >&2
      echo "---- end pytest output ----" >&2
      die "$m failed exit-gate check 4: pytest is now red (rerun: cd python-replica && pytest). NOTE: if $m was already committed in a previous run, the baseline may have regressed since — inspect commits AFTER $m with: git -C python-replica log --oneline -- src/ tests/ | head -20"
    fi
  fi
}

check_progress_block() {
  local m="$1"

  if ! grep -qE "^## ${m} — done [0-9]{4}-[0-9]{2}-[0-9]{2}" \
       "$REPLICA_DIR/initiatives/current/PROGRESS.md" 2>/dev/null; then
    die "$m failed exit-gate check 3: no '## $m — done YYYY-MM-DD' block found in initiatives/current/PROGRESS.md (exit ritual step 3 skipped or format wrong)"
  fi
}

check_handoff_touched_in_commit() {
  local m="$1"
  local commit="$2"

  if ! git -C "$REPLICA_DIR" log -1 --name-only --pretty=format: "$commit" \
       | grep -qx "initiatives/current/HANDOFF.md"; then
    die "$m failed exit-gate check 2: initiatives/current/HANDOFF.md was not modified in commit $commit (exit ritual step 4 skipped)"
  fi
}

# Check 6: enforce the append-only contract on PROGRESS.md and
# HANDOFF.md Section 2. Both files must still carry every prior
# milestone's record. Without this, a milestone agent that rewrote
# either file from scratch (erasing M1..M{N-1}'s real history) would
# slip past checks 1-5 — only the current M{N}'s block is needed to
# satisfy check 3, and checks 1/2/4/5 do not look at prior content.
#
# Prior milestones are discovered by walking baseline_commit..HEAD for
# `[<prefix>/M*]` commits (matching find_milestone_commit's range, so
# a prior archived initiative reusing the same prefix cannot leak in).
check_prior_milestones_preserved() {
  local m="$1"
  local prior
  local prior_subjects

  prior_subjects="$(git -C "$REPLICA_DIR" log "${BASELINE_COMMIT}..HEAD" \
                    --format='%s' | grep -F "[${COMMIT_PREFIX}/" || true)"
  [ -n "$prior_subjects" ] || return 0  # no prior milestones yet (M1 case)

  while IFS= read -r prior_subject; do
    [ -n "$prior_subject" ] || continue
    # Extract M_ID from "[<prefix>/M_ID] ..." -> after the slash, before the close bracket
    prior="$(printf '%s\n' "$prior_subject" \
             | sed -nE "s|^\[${COMMIT_PREFIX}/(M[0-9]+)\].*$|\1|p" \
             | head -1)"
    [ -n "$prior" ] || continue
    [ "$prior" = "$m" ] && continue  # skip the current milestone (it just appended itself)

    if ! grep -qE "^## ${prior} — done [0-9]{4}-[0-9]{2}-[0-9]{2}" \
         "$REPLICA_DIR/initiatives/current/PROGRESS.md" 2>/dev/null; then
      die "$m failed exit-gate check 6: PROGRESS.md no longer contains the '## ${prior} — done' block from the previous milestone — current milestone rewrote PROGRESS.md instead of appending (violates the append-only contract documented in automation/templates/progress_entry.md)"
    fi
    if ! grep -qE "^### ${prior}$" \
         "$REPLICA_DIR/initiatives/current/HANDOFF.md" 2>/dev/null; then
      die "$m failed exit-gate check 6: HANDOFF.md Section 2 no longer contains the '### ${prior}' subsection from the previous milestone — current milestone rewrote HANDOFF Section 2 instead of appending (violates the append-only contract documented in automation/templates/handoff_milestone.md)"
    fi
  done <<< "$prior_subjects"
}

milestone_already_complete() {
  local m="$1"
  local commit

  commit="$(find_milestone_commit "$m")"
  [ -n "$commit" ] || return 1

  check_handoff_touched_in_commit "$m" "$commit"
  check_progress_block "$m"
  check_pytest_green "$m"
  check_handoff_structure "$m"
  check_prior_milestones_preserved "$m"

  printf '=== %s already complete at %s; skipping ===\n' "$m" "${commit:0:7}"
  return 0
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
BASELINE_COMMIT=$(read_config_scalar "baseline_commit")

[ -n "$INITIATIVE_SLUG" ]   || die "slug missing from $CONFIG"
[ -n "$COMMIT_PREFIX" ]     || die "commit_prefix missing from $CONFIG"
# commit_prefix is interpolated into sed -E regexes (see check_prior_milestones_preserved
# and the review-template substitution); reject anything that could corrupt those regexes.
if ! printf '%s' "$COMMIT_PREFIX" | grep -qE '^[a-z0-9][a-z0-9_-]{0,31}$'; then
  die "commit_prefix '$COMMIT_PREFIX' in $CONFIG must match ^[a-z0-9][a-z0-9_-]{0,31}\$ — it is interpolated into sed -E regexes, so regex meta-chars (|, [, \\, *, +, ?, ., etc.) are unsafe"
fi
[ -n "$ARCHIVE_SLUG" ]      || die "archive_slug missing from $CONFIG"
[ -n "$BASELINE_COMMIT" ]   || die "baseline_commit missing from $CONFIG (Phase 1 Step 5 records it as 'git rev-parse HEAD' at Phase 1 entry; pre-RUNBOOK config.yaml files lack this field — rebootstrap or add 'baseline_commit: <baseline SHA>' to $CONFIG manually)"

# Defense: baseline_commit must be an ancestor of HEAD. If a branch has
# been rebased / cherry-picked / hard-reset since Phase 1, baseline_commit
# may no longer be reachable, and 'git log baseline_commit..HEAD' would
# silently produce a wrong (often empty) commit set.
if ! git -C "$REPLICA_DIR" merge-base --is-ancestor "$BASELINE_COMMIT" HEAD 2>/dev/null; then
  die "baseline_commit $BASELINE_COMMIT in $CONFIG is not an ancestor of HEAD — the branch may have been rebased, cherry-picked, or hard-reset since Phase 1; investigate before proceeding"
fi

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
  if [ -n "$(git -C "$REPLICA_DIR" status --porcelain)" ]; then
    git -C "$REPLICA_DIR" status --short
    die "working tree in $REPLICA_DIR is dirty — commit, stash, or remove untracked files, then retry (untracked files are NOT exempt: a half-bootstrapped initiatives/current/ or a crashed milestone agent leaving new test files would silently pollute Phase 2; see RUNBOOK Pre-flight)"
  fi
  printf 'OK         : working tree clean (no tracked diffs, no untracked files)\n'
fi

mkdir -p "$LOGS_DIR"

# Notify: pre-flight passed, milestone loop is about to start.
notify "🚀 Initiative started" \
"$(notify_run_context)

Milestones queued: ${#MILESTONES[@]}
  ${MILESTONES[*]}

Started: $(date)" \
  "rocket" "low"

# ---------------------------------------------------------------------------
# Execute milestones (Phase 2A)
# ---------------------------------------------------------------------------

for M in "${MILESTONES[@]}"; do
  PROMPT="$PROMPTS_DIR/$M.md"
  [ -f "$PROMPT" ] || die "prompt missing for $M: $PROMPT"

  if [ "$DRY_RUN" -eq 0 ] && milestone_already_complete "$M"; then
    continue
  fi

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
  # `tee "$LOG"` creates the file only after claude emits its first byte.
  # Pre-touching it lets the operator run `tail -F` *immediately* after
  # seeing the Live view line, without macOS BSD tail bailing out with
  # "No such file or directory" on a not-yet-existent path.
  : > "$LOG"
  printf 'Prompt     : %s\n' "$PROMPT"
  printf 'Log        : %s\n' "$LOG"
  # tail -F (uppercase) follows by name and retries on rename/truncate,
  # so it stays robust if the file is rotated or recreated mid-run.
  printf 'Live view  : tail -F %s\n\n' "$LOG"

  MILESTONE_STARTED_AT="$(date +%s)"
  CURRENT_STAGE="milestone ${M}: running claude"
  CURRENT_LOG="$LOG"

  notify "🚀 Started ${M}" \
"$(notify_run_context)

Milestone: ${M}
Queue: ${MILESTONES[*]}
Prompt: ${PROMPT}
Log: ${LOG}

Git status before run:
$(git_dirty_summary)

Started: $(date)" \
    "rocket" "default"

  # --verbose: stream tool calls and intermediate progress to stdout so
  # the operator can monitor a long autonomous run live AND the log
  # captures something useful even if the session terminates before
  # `end_turn` (e.g. Claude Code's auto-compact thrash-loop protection;
  # see anthropics/claude-code#41796). Without --verbose, --print only
  # emits the final response text — a session that never reaches
  # end_turn produces a 0/1-byte log, making post-mortem debugging hard.
  if ! claude --print --verbose --model "$CLAUDE_MODEL" \
       --allowedTools "$ALLOWED_TOOLS" \
       --disallowedTools "$DISALLOWED_TOOLS" \
       < "$PROMPT" 2>&1 | tee "$LOG"; then
    die "$M: claude invocation exited non-zero (see $LOG)"
  fi

  # ------------------------------------------------------------------------
  # Exit-gate: 6 independent checks. ALL must pass or the loop halts.
  # See automation/RUNBOOK.md Phase 2A for the full spec.
  # ------------------------------------------------------------------------

  # Check 1: commit subject contains [<commit_prefix>/<M>]
  if ! git -C "$REPLICA_DIR" log --oneline -1 | grep -qF "[${COMMIT_PREFIX}/${M}]"; then
    git -C "$REPLICA_DIR" log --oneline -5
    die "$M failed exit-gate check 1: no '[${COMMIT_PREFIX}/${M}]' commit at HEAD"
  fi

  # Check 2: HANDOFF.md was modified in that commit (exit ritual step 4)
  check_handoff_touched_in_commit "$M" "HEAD"

  # Check 3: PROGRESS.md contains a '## M{N} — done YYYY-MM-DD' block
  # (exit ritual step 3). Use anchored regex so e.g. M1 does NOT match
  # M10 / M11 / etc., and so a bare "M1" appearing in a notes line does
  # not satisfy the gate.
  check_progress_block "$M"

  # Check 4: pytest still green (unless --skip-quality). The agent already
  # runs pytest before commit per §4, but we trust-but-verify here so a
  # skipped or flaky agent run does not propagate to the next milestone.
  check_pytest_green "$M"

  # Check 5: HANDOFF.md has the 5-section structure (proves the agent
  # used automation/templates/handoff_milestone.md, not a free-form
  # HANDOFF). Each section header must be present verbatim.
  check_handoff_structure "$M"

  # Check 6: append-only contract on PROGRESS.md and HANDOFF.md Section
  # 2 — every prior milestone (baseline_commit..HEAD, same range
  # find_milestone_commit uses) must still have its '## M{i} — done'
  # PROGRESS block and '### M{i}' HANDOFF subsection. Without this, a
  # milestone that rewrote either file from scratch would erase the
  # real history of M1..M{N-1} and still pass checks 1-5.
  check_prior_milestones_preserved "$M"

  printf '\n=== %s done at %s ===\n' "$M" "$(date)"

  CURRENT_STAGE="milestone ${M}: completed"

  LAST_COMMIT="$(git -C "$REPLICA_DIR" log --oneline -1 2>/dev/null || true)"
  CHANGED_FILES="$(git -C "$REPLICA_DIR" show --name-only --pretty=format: HEAD 2>/dev/null | sed '/^$/d' | head -30 || true)"

  notify "✅ Completed ${M}" \
"$(notify_run_context)

Milestone: ${M}
Milestone elapsed: $(duration_since "$MILESTONE_STARTED_AT")
Commit: ${LAST_COMMIT}
Log: ${LOG}

Changed files:
${CHANGED_FILES:-none}

Last log lines:
$(log_tail_summary "$LOG" 12)

Completed: $(date)" \
    "white_check_mark,git" "default"
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

mkdir -p "$SCRATCH_LOGS_DIR"

# Keep the live review stdout outside initiatives/current. The review agent
# moves current/ into _archive/ and commits while claude --print is still
# streaming; writing the live tee directly into the archive would dirty the
# just-created wrap commit after it lands.
REVIEW_LOG="$SCRATCH_LOGS_DIR/${ARCHIVE_SLUG}-review.log"
REVIEW_PROMPT="$LOGS_DIR/review_prompt.md"

# Substitute initiative-specific tokens into the review template.
sed \
  -e "s|{{INITIATIVE_SLUG}}|$INITIATIVE_SLUG|g" \
  -e "s|{{COMMIT_PREFIX}}|$COMMIT_PREFIX|g" \
  -e "s|{{ARCHIVE_SLUG}}|$ARCHIVE_SLUG|g" \
  -e "s|{{BASELINE_COMMIT}}|$BASELINE_COMMIT|g" \
  "$REVIEW_TEMPLATE" > "$REVIEW_PROMPT"

# Pre-touch so `tail -F` works immediately — same rationale as the
# per-milestone log pre-touch above.
: > "$REVIEW_LOG"
printf 'Review prompt : %s\n' "$REVIEW_PROMPT"
printf 'Review log    : %s\n' "$REVIEW_LOG"
printf 'Live view     : tail -F %s\n\n' "$REVIEW_LOG"

CURRENT_STAGE="review: running claude"
CURRENT_LOG="$REVIEW_LOG"

notify "🔍 Started final review" \
"$(notify_run_context)

Review prompt: ${REVIEW_PROMPT}
Review log: ${REVIEW_LOG}
Archive target: initiatives/_archive/${ARCHIVE_SLUG}

Started: $(date)" \
  "mag" "default"

# --verbose: same rationale as the per-milestone invocation above —
# stream progress so the review log is informative even on early
# termination.
if ! claude --print --verbose --model "$CLAUDE_MODEL" \
     --allowedTools "$ALLOWED_TOOLS" \
     --disallowedTools "$DISALLOWED_TOOLS" \
     < "$REVIEW_PROMPT" 2>&1 | tee "$REVIEW_LOG"; then
  die "review session exited non-zero (see $REVIEW_LOG)"
fi

# Exit gate for the review session. ALL checks must pass.
if ! git -C "$REPLICA_DIR" log --oneline -1 | grep -qF "[${COMMIT_PREFIX}/wrap]"; then
  git -C "$REPLICA_DIR" log --oneline -5
  die "review wrap-gate check 1 failed: no '[${COMMIT_PREFIX}/wrap]' commit at HEAD"
fi

if [ ! -d "$REPLICA_DIR/initiatives/_archive/$ARCHIVE_SLUG" ]; then
  die "review wrap-gate check 2 failed: archive dir missing at initiatives/_archive/$ARCHIVE_SLUG"
fi

if [ ! -f "$REPLICA_DIR/initiatives/_archive/$ARCHIVE_SLUG/REVIEW.md" ]; then
  die "review wrap-gate check 3 failed: REVIEW.md missing from initiatives/_archive/$ARCHIVE_SLUG"
fi

if [ ! -f "$CURRENT_DIR/.gitkeep" ]; then
  die "review wrap-gate check 4 failed: initiatives/current/.gitkeep was not recreated"
fi

CURRENT_CONTENTS=$(find "$CURRENT_DIR" -mindepth 1 -maxdepth 1 ! -name .gitkeep -print)
if [ -n "$CURRENT_CONTENTS" ]; then
  printf '%s\n' "$CURRENT_CONTENTS" >&2
  die "review wrap-gate check 5 failed: initiatives/current contains files other than .gitkeep"
fi

if [ -n "$(git -C "$REPLICA_DIR" status --short)" ]; then
  git -C "$REPLICA_DIR" status --short
  die "review wrap-gate check 6 failed: working tree dirty after wrap commit (Tier A/B edits may not have been staged)"
fi

ARCHIVED_REVIEW_LOG="$REPLICA_DIR/initiatives/_archive/$ARCHIVE_SLUG/logs/review.log"
if [ ! -f "$REVIEW_LOG" ]; then
  die "review log archival failed: scratch review log missing at $REVIEW_LOG"
fi

mkdir -p "$(dirname "$ARCHIVED_REVIEW_LOG")"
cp "$REVIEW_LOG" "$ARCHIVED_REVIEW_LOG"
git -C "$REPLICA_DIR" add "initiatives/_archive/$ARCHIVE_SLUG/logs/review.log"
if ! git -C "$REPLICA_DIR" diff --cached --quiet -- "initiatives/_archive/$ARCHIVE_SLUG/logs/review.log"; then
  git -C "$REPLICA_DIR" commit --amend --no-edit
fi

if ! git -C "$REPLICA_DIR" log --oneline -1 | grep -qF "[${COMMIT_PREFIX}/wrap]"; then
  git -C "$REPLICA_DIR" log --oneline -5
  die "review log archival failed: amended commit no longer has '[${COMMIT_PREFIX}/wrap]' subject"
fi

if [ -n "$(git -C "$REPLICA_DIR" status --short)" ]; then
  git -C "$REPLICA_DIR" status --short
  die "review log archival failed: working tree dirty after adding archived review.log"
fi

printf '\n================================================================\n'
printf '=== Initiative %s complete at %s ===\n' "$INITIATIVE_SLUG" "$(date)"
printf '================================================================\n'

CURRENT_STAGE="initiative complete"

FINAL_COMMIT="$(git -C "$REPLICA_DIR" log --oneline -1 2>/dev/null || true)"
RECENT_COMMITS="$(git -C "$REPLICA_DIR" log --oneline -8 2>/dev/null || true)"

notify "🎉 Initiative complete: ${INITIATIVE_SLUG}" \
"$(notify_run_context)

Total elapsed: $(duration_since "$RUN_STARTED_AT")
Final commit: ${FINAL_COMMIT}
Archive: initiatives/_archive/${ARCHIVE_SLUG}
Review: initiatives/_archive/${ARCHIVE_SLUG}/REVIEW.md
Review log: initiatives/_archive/${ARCHIVE_SLUG}/logs/review.log

Recent commits:
${RECENT_COMMITS}

Last review log lines:
$(log_tail_summary "$REVIEW_LOG" 20)

Completed: $(date)" \
  "tada,package" "high"

git -C "$REPLICA_DIR" log --oneline -10
printf '\nREVIEW.md : initiatives/_archive/%s/REVIEW.md\n' "$ARCHIVE_SLUG"

if [ -f "$ARCHIVED_REVIEW_LOG" ]; then
  printf '\n=== Review log tail (last 60 lines) ===\n'
  tail -60 "$ARCHIVED_REVIEW_LOG"
fi
