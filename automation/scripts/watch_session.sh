#!/usr/bin/env bash
# watch_session.sh -- Live-tail the JSON-lines transcript of the most active
# `claude --print` subprocess and translate each event into a one-line-per-event
# compact view. Useful for watching milestones run when
# `run_all_milestones.sh` is going in the background.
#
# WHY THIS EXISTS
#   `claude --print --verbose` writes plain-text agent output (and only the
#   text-response blocks) to stdout, captured by run_all_milestones.sh's
#   `tee initiatives/current/logs/M{N}.log`. Tool calls, tool results, and
#   thinking turns never reach that log -- so `tail -F M{N}.log` shows
#   nothing while the agent is doing tool work.
#
#   Claude CLI also writes a full JSON-lines transcript to
#   `~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl` that DOES contain
#   every event. This script finds that file for the active `claude --print`
#   subprocess (via lsof on the PID) and pipes it through an inline Python
#   parser that prints one line per assistant text / tool_use / tool_result.
#
# USAGE
#   In a separate terminal, while run_all_milestones.sh is going:
#       ./automation/scripts/watch_session.sh
#
#   Example output:
#       [A tool] Read(file_path=/Users/leng/my-cc-py/python-replica/src/...)
#       [U tool_result len=326]
#       [A text] Default behavior preserved. Now adding the keep_recent=1 case.
#       [A tool] Edit(replace_all=False)
#       [U tool_result ERR len=649]
#
# MILESTONE-TO-MILESTONE BOUNDARY
#   Each milestone in run_all_milestones.sh spawns a fresh `claude --print`
#   with a brand-new session UUID, so the jsonl path changes between M1/M2/M3.
#   `tail -F` follows by inode, not by name, so it WILL NOT auto-switch to the
#   next milestone's jsonl. Press ^C between milestones and re-run this
#   script -- it re-resolves the active PID + jsonl each time.
#
# EXIT CODES
#   0  Normal termination (^C from the user).
#   1  No `claude --print` process found, or PID has no .jsonl open yet
#      (still initialising -- retry in a few seconds).

set -euo pipefail

# Find the active claude --print PID.
PID="$(pgrep -f 'claude --print' | head -1 || true)"
if [ -z "$PID" ]; then
    echo "watch_session: no active 'claude --print' process found." >&2
    echo "Start ./automation/scripts/run_all_milestones.sh in another terminal first," >&2
    echo "or run a single milestone manually via run_next.sh." >&2
    exit 1
fi

# Find the .jsonl transcript file that PID has open.
# lsof on macOS prints the path in the last column.
JSONL="$(lsof -p "$PID" 2>/dev/null | awk '/\.jsonl$/{print $NF}' | head -1 || true)"
if [ -z "$JSONL" ]; then
    echo "watch_session: PID $PID is a 'claude --print' process, but has no" >&2
    echo "  .jsonl transcript open yet. It is probably still initialising." >&2
    echo "  Retry in a few seconds." >&2
    exit 1
fi

echo "watch_session: PID=$PID" >&2
echo "watch_session: file=$JSONL" >&2
echo "(^C to stop; re-run between milestones to pick up the new session UUID)" >&2
echo >&2

# tail -F follows the file by name; if claude rotates / re-opens it the tail
# survives. We pipe each JSON line through a Python parser that prints one
# compact line per event:
#   [A text]              assistant text response (truncated to 160 chars)
#   [A tool] name(k=v)    assistant tool_use   (first kwarg only, value <=80 chars)
#   [U tool_result len=N] user/tool_result; ERR prefix if is_error=true
# Anything that does not match (system messages, queue-operation, partial
# message chunks, malformed lines) is silently dropped.
exec tail -F "$JSONL" | python3 -u -c '
import sys, json
for line in sys.stdin:
    try:
        e = json.loads(line); t = e.get("type","?")
        if t == "assistant":
            for b in e.get("message",{}).get("content",[]):
                if not isinstance(b,dict): continue
                if b.get("type") == "text":
                    txt = b.get("text","").replace("\n"," ")[:160]
                    if txt: print(f"[A text] {txt}", flush=True)
                elif b.get("type") == "tool_use":
                    name = b.get("name"); inp = b.get("input",{}) or {}
                    k = next(iter(inp), ""); v = str(inp.get(k,""))[:80].replace("\n"," ")
                    print(f"[A tool] {name}({k}={v})", flush=True)
        elif t == "user":
            for b in e.get("message",{}).get("content",[]) or []:
                if isinstance(b,dict) and b.get("type") == "tool_result":
                    c = b.get("content","")
                    if isinstance(c,list): c = " ".join(str(x)[:60] for x in c[:1])
                    err = "ERR " if b.get("is_error") else ""
                    print(f"[U tool_result {err}len={len(str(c))}]", flush=True)
    except Exception: pass
'
