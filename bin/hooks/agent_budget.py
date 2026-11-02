#!/usr/bin/env python3
"""PreToolUse hook: the run budget of CLAUDE.md, enforced. Subagents only; the main session passes.

Each agent gets LIMIT_CALLS tool calls, LIMIT_MIN minutes and LIMIT_TOKENS of context (read from its own transcript;
unreadable counts as 0). Past any of them only closing moves are allowed, GRACE of them: a git command, or a write to
docs/state/. After that every call is refused. State: one JSON per agent in $AGENT_BUDGET_DIR.
A broken hook must not stop work: any error here exits 0 and lets the call through.
"""
import json
import os
import re
import sys
import time

LIMIT_CALLS, LIMIT_MIN, LIMIT_TOKENS, GRACE = 100, 90, 250_000, 20
STATE = os.environ.get("AGENT_BUDGET_DIR", "/mnt/data/hifipushie/agent_budget")


def context_tokens(path):
    """The latest assistant turn's context size in a transcript, 0 if it can't be read."""
    if not path or not os.path.exists(path):
        return 0
    with open(path, "rb") as f:
        f.seek(max(0, os.path.getsize(path) - 256_000))
        lines = f.read().split(b"\n")
    for line in reversed(lines):
        if b'"usage"' not in line:
            continue
        try:
            u = json.loads(line)["message"]["usage"]
        except (ValueError, KeyError, TypeError):
            continue
        return u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
    return 0


def closing_move(tool, args):
    if tool == "Bash":
        return re.match(r"\s*(cd \S+\s*(&&|;)\s*)?git\s", args.get("command", "")) is not None
    return tool in ("Write", "Edit") and "/docs/state/" in args.get("file_path", "")


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))


def main():
    hook = json.load(sys.stdin)
    agent = hook.get("agent_id")
    if not agent:
        return
    os.makedirs(STATE, exist_ok=True)
    path = os.path.join(STATE, re.sub(r"\W", "_", agent) + ".json")
    s = {"calls": 0, "start": time.time(), "closing": 0}
    if os.path.exists(path):
        with open(path) as f:
            s = json.load(f)
    s["calls"] += 1
    minutes = (time.time() - s["start"]) / 60
    # transcript_path is the parent session's, never count that: the agent's own sits beside it
    tokens = context_tokens(re.sub(r"\.jsonl$", "", hook.get("transcript_path", "")) + f"/subagents/agent-{agent}.jsonl")
    over = [t for t, bad in ((f"{s['calls']} tool calls (limit {LIMIT_CALLS})", s["calls"] > LIMIT_CALLS),
                             (f"{minutes:.0f} min (limit {LIMIT_MIN})", minutes > LIMIT_MIN),
                             (f"{tokens // 1000}k context (limit {LIMIT_TOKENS // 1000}k)", tokens > LIMIT_TOKENS)) if bad]
    if over:
        if closing_move(hook.get("tool_name", ""), hook.get("tool_input") or {}) and s["closing"] < GRACE:
            s["closing"] += 1
        else:
            deny(f"Run budget spent: {', '.join(over)}. Stop working: commit what you have (git), write your STATE page under "
                 f"docs/state/ with its NEXT line, and end your run with a report. Closing moves left: {GRACE - s['closing']}.")
    with open(path, "w") as f:
        json.dump(s, f)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never stop work over a broken hook
        print(f"agent_budget: {e}", file=sys.stderr)
