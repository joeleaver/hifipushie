#!/usr/bin/env python3
"""audit: grade one worker agent's session (docs/notes/audit.md).

  audit <agent-id | transcript.jsonl> [--out DIR] [--no-grade] [--model M]

1. DIGEST (no LLM): the JSONL as compact text (brief, one line per tool call, coordinator messages, the final
   report; no images / base64, long outputs cut) + OBJECTIVE metrics (tool calls, peak context, wall time,
   reviews and verdicts, remote submits, local renders capped or not, errors, repeats, commits, git add -A,
   whole reads of big notes, polls, $ mentions).
2. GRADE: ONE headless `claude -p` call (no tools, no settings, minimal system prompt) on the digest + metrics +
   docs/notes/audit_rubric.md + the process files (gates.md, RESTART.txt) with line numbers. Returns JSON.
Writes DIR/{digest.txt, metrics.json, audit.json, audit.md, grade_raw.txt} (default
/mnt/data/hifipushie/audits/<id>/) and puts one row for the id in /mnt/data/hifipushie/audits/index.tsv.
Audits name private subjects: they stay in /mnt/data, never in git.
"""
import datetime as dt
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict

REPO = "/home/joe/dev/hifipushie"
SUBAGENTS = "/home/joe/.claude/projects/-home-joe-dev-hifipushie/8abf1c05-bdfa-497a-8337-5980e7190374/subagents"
AUDITS = "/mnt/data/hifipushie/audits"
RUBRIC = os.path.join(REPO, "docs/notes/audit_rubric.md")
PROCESS_GIT = ["docs/notes/gates.md"]                  # shown as of the session's start (git)
PROCESS_FILES = ["/mnt/data/hifipushie/bin/RESTART.txt"]  # not in git: dated sections
PROCESS_GREP = [("src/hifipushie/guide_spec.md", r"sewn|never in the solver|by hand|sculpt")]
DIGEST_BUDGET = 95_000          # chars (~24k tokens)
CTX_LIMIT = 250_000             # agent context budget (memory: agent-context-budget)
BIG_FILE = 40_000               # bytes: a whole read of a notes file this big is a context fault
INDEX_COLS = ["audited", "id", "role", "start", "wall_h", "tool_calls", "peak_ctx", "reviews", "pass", "fail",
              "rounds_to_pass", "remote_submits", "remote_over_12g", "errors", "repeat_fails", "commits",
              "git_add_all", "big_reads", "polls", "adherence_mean", "n_process", "n_tooling", "grade_in_tok",
              "grade_out_tok", "grade_usd", "verdict"]


def one(s, n):
    s = re.sub(r"\s+", " ", str(s)).strip()
    s = re.sub(r"[A-Za-z0-9+/=]{200,}", "[base64]", s)
    return s if len(s) <= n else s[: n - 3] + "..."


def result_text(c):
    """A tool_result's content as text, images dropped."""
    c = c.get("content")
    if isinstance(c, str):
        return c
    out = []
    for b in c or []:
        if b.get("type") == "text":
            out.append(b.get("text", ""))
        elif b.get("type") == "image":
            out.append("[image]")
    return "\n".join(out)


def short_input(name, inp):
    if name == "Bash":
        c = re.sub(r"<<-?\s*['\"]?(\w+)['\"]?.*?\n\1\b",
                   lambda m: f"<<{m.group(1)} [{m.group(0).count(chr(10)) - 1} lines]", inp.get("command", ""), flags=re.S)
        return ("[bg] " if inp.get("run_in_background") else "") + c
    if name == "Read":
        s = inp.get("file_path", "")
        if inp.get("offset") or inp.get("limit"):
            s += f" @{inp.get('offset', 0)}+{inp.get('limit', '')}"
        return s + (f" pages={inp['pages']}" if inp.get("pages") else "")
    if name in ("Edit", "Write", "NotebookEdit"):
        n = len(inp.get("new_string", inp.get("content", "")) or "")
        return f"{inp.get('file_path', '')} ({n} chars)"
    if name in ("Grep", "Glob"):
        return f"{inp.get('pattern', '')} {inp.get('path', '')}"
    if name == "SendMessage":
        return f"to={inp.get('to')} {inp.get('summary', '')}"
    if name == "Agent":
        return f"{inp.get('subagent_type', '')}: {inp.get('description', '')}"
    if name == "Monitor":
        return inp.get("command", json.dumps(inp))
    if name == "ToolSearch":
        return inp.get("query", "")
    return json.dumps(inp)


NOTABLE = re.compile(r"VERDICT|Traceback|Error|error:|Killed|exit code 137|FAIL|PASS|alive|dead|queued|running|"
                     r"status|sha256|refus|timed? ?out|\$\d", re.I)


def snippet(text, n):
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return ""
    hits = [l for l in lines if NOTABLE.search(l)]
    pick = hits[-2:] if hits else lines[-1:]
    return one(" | ".join(pick), n)


# ---------------------------------------------------------------- parse

def load(path):
    rows = []
    for l in open(path):
        l = l.strip()
        if l:
            try:
                rows.append(json.loads(l))
            except json.JSONDecodeError:
                pass
    return rows


def ts(o):
    t = o.get("timestamp")
    return dt.datetime.fromisoformat(t.replace("Z", "+00:00")) if t else None


def parse(path):
    """Events in order: brief, calls (with results), texts, inbound messages, context marks."""
    rows = load(path)
    brief, calls, events, times, ctx = None, {}, [], [], []
    for o in rows:
        t = ts(o)
        if t:
            times.append(t)
        m = o.get("message") if isinstance(o.get("message"), dict) else None
        if o.get("type") == "user" and m is not None:
            c = m.get("content")
            if isinstance(c, str):
                if brief is None and not o.get("isMeta"):
                    brief = c
                elif not o.get("isMeta") and "<system-reminder>" not in c[:40]:
                    events.append(("in", "user", c, t))
            else:
                for b in c or []:
                    if b.get("type") == "tool_result":
                        cid = b.get("tool_use_id")
                        if cid in calls:
                            calls[cid]["out"] = result_text(b)
                            calls[cid]["err"] = bool(b.get("is_error"))
                    elif b.get("type") == "text" and brief is None:
                        brief = b.get("text", "")
        elif o.get("type") == "assistant" and m is not None:
            u = m.get("usage") or {}
            if u:
                c = (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + \
                    (u.get("cache_creation_input_tokens") or 0)
                ctx.append((c, u.get("output_tokens") or 0, m.get("id") or o.get("requestId")))
                events.append(("ctx", c, None, t))
            for b in m.get("content") or []:
                if b.get("type") == "tool_use":
                    d = {"id": b["id"], "name": b["name"], "input": b.get("input") or {}, "out": "", "err": False,
                         "t": t}
                    calls[b["id"]] = d
                    events.append(("call", d, None, t))
                elif b.get("type") == "text" and b.get("text", "").strip():
                    events.append(("say", b["text"], None, t))
        elif o.get("type") == "attachment":
            a = o.get("attachment") or {}
            if a.get("type") == "queued_command":
                p = a.get("prompt", "")
                if isinstance(p, list):
                    p = " ".join(x.get("text", "") for x in p if isinstance(x, dict))
                kind = (a.get("origin") or {}).get("kind", "")
                if "<task-notification>" in p:
                    st = re.search(r"<status>(.*?)</status>", p, re.S)
                    su = re.search(r"<summary>(.*?)</summary>", p, re.S)
                    events.append(("in", "task", f"{st.group(1) if st else '?'}: {su.group(1) if su else ''}", t))
                else:
                    events.append(("in", kind or "queued", p, t))
    # dedupe usage rows that repeat per content block (same message id)
    seen, peak, outs = set(), 0, 0
    for c, o_, mid in ctx:
        if mid in seen:
            continue
        seen.add(mid)
        peak = max(peak, c)
        outs += o_
    return {"brief": brief or "", "events": events, "calls": list(calls.values()), "times": times,
            "peak": peak, "out_tokens": outs, "rows": len(rows)}


# ---------------------------------------------------------------- metrics

def main_path(p):
    return re.sub(r"/\.claude/worktrees/[^/]+/", "/", p)


def is_invocation(cmd, word):
    """cmd runs `word` (not just cat/sed/grep of it)."""
    for part in re.split(r"&&|\|\|?|;|\n", cmd):
        part = part.strip()
        if word in part and not re.match(r"(cat|sed|head|tail|less|grep|rg|wc|ls|cp|diff|vi|nano|echo|git)\b", part):
            return True
    return False


def metrics(P):
    calls = P["calls"]
    M = {"rows": P["rows"], "tool_calls": len(calls), "by_tool": dict(Counter(c["name"] for c in calls).most_common()),
         "peak_ctx": P["peak"], "over_ctx_limit": P["peak"] > CTX_LIMIT, "out_tokens": P["out_tokens"]}
    t = P["times"]
    M["start"] = t[0].isoformat(timespec="minutes") if t else ""
    M["end"] = t[-1].isoformat(timespec="minutes") if t else ""
    M["wall_h"] = round((t[-1] - t[0]).total_seconds() / 3600, 2) if t else 0
    bash = [c for c in calls if c["name"] == "Bash"]
    cmd = lambda c: c["input"].get("command", "")
    # reviews and verdicts
    M["review_runs"] = sum(1 for c in bash if re.search(r"bin/review\b|\brev\w*\.sh\b|review\.sh\b", cmd(c))
                           and (is_invocation(cmd(c), "review") or is_invocation(cmd(c), "rev")))
    verdicts = []
    for i, c in enumerate(calls):
        for v in re.findall(r"^[\s*#>]*VERDICT:\s*(PASS|FAIL)\W*$", c["out"] or "", re.M):
            verdicts.append((i + 1, v))
    M["verdicts"] = [f"#{i}:{v}" for i, v in verdicts]
    M["pass"] = sum(v == "PASS" for _, v in verdicts)
    M["fail"] = sum(v == "FAIL" for _, v in verdicts)
    M["rounds_to_pass"] = next((k + 1 for k, (_, v) in enumerate(verdicts) if v == "PASS"), None)
    # remote / sims
    rem, over = [], []
    for i, c in enumerate(calls, 1):
        s = cmd(c) if c["name"] == "Bash" else (json.dumps(c["input"]) if "dress" in c["name"] else "")
        if not s:
            continue
        if is_invocation(s, "remote.sh") or is_invocation(s, "bundle_client") or "dress" in c["name"]:
            rem.append(i)
            m = re.search(r"remote\.sh\s+\S+\s+\S+\s+(\d+)", s)
            if m and int(m.group(1)) > 12:
                over.append(f"#{i}:{m.group(1)}GB")
        for m in re.finditer(r"ram_gb\D{0,4}(\d+)", s):
            if int(m.group(1)) > 12:
                over.append(f"#{i}:ram_gb={m.group(1)}")
    M["remote_submits"] = len(rem)
    M["remote_calls"] = rem[:40]
    M["remote_over_12g"] = over
    M["sim_mentions"] = sum(1 for c in bash if re.search(r"\b(sim|zozo|drape|cloth_run|dress)\w*", cmd(c)))
    # local renders and caps
    def body(c):  # the command without heredoc bodies (scripts being written, not run)
        return re.sub(r"<<-?\s*['\"]?(\w+)['\"]?.*?\n\1\b", " ", cmd(c), flags=re.S)
    wrapped = lambda s: re.search(r"\bcapped\b|bin/slot\b|\b(run|q|rr|plr|p)\.sh\b", s)
    blender_run = re.compile(r"(^|[\s;&|(])(\S*/)?blender\s+(-b\b|--background|-P\b|--python|\S+\.blend)")
    blend = [i for i, c in enumerate(calls, 1) if c["name"] == "Bash" and blender_run.search(body(c))
             and "remote.sh" not in cmd(c)]
    M["local_blender"] = len(blend)
    M["local_blender_uncapped"] = [i for i in blend if not wrapped(body(calls[i - 1]))]
    heavy = [i for i, c in enumerate(calls, 1) if c["name"] == "Bash" and not wrapped(body(c)) and
             (i in blend or re.search(r"\buv run (python3? )?(?!-c\b)\S+\.py\b|-m hifipushie\b", body(c)))]
    M["uncapped_heavy"] = heavy[:30]
    M["mcp_look_calls"] = sum(1 for c in calls if c["name"].endswith("__look"))
    # errors and repeats
    errs = [i for i, c in enumerate(calls, 1) if c["err"]]
    M["errors"] = len(errs)
    fk = Counter(one(short_input(c["name"], c["input"]), 200) for c in calls if c["err"])
    M["repeat_fails"] = {k: n for k, n in fk.items() if n >= 2}
    allk = Counter(one(short_input(c["name"], c["input"]), 200) for c in calls)
    M["repeat_calls"] = {k: n for k, n in allk.most_common(8) if n >= 3}
    # git
    M["commits"] = sum(1 for c in bash if re.search(r"git commit\b", cmd(c)))
    M["git_add_all"] = [i for i, c in enumerate(calls, 1) if c["name"] == "Bash" and
                        re.search(r"git add\s+(-A|--all|\.(\s|$|;|&))", cmd(c))]
    M["pushes"] = sum(1 for c in bash if re.search(r"git push\b", cmd(c)))
    # big whole reads
    big = []
    for i, c in enumerate(calls, 1):
        paths = []
        if c["name"] == "Read" and not c["input"].get("limit"):
            paths = [c["input"].get("file_path", "")]
            paths = [p for p in paths if not re.search(r"\.(png|jpe?g|webp|gif|pdf)$", p, re.I)]
        elif c["name"] == "Bash":
            for m in re.finditer(r"(?:^|[;&|]\s*)cat\s+([^\s|;&]+\.(?:md|txt))(?!\s*\|)", cmd(c)):
                paths.append(m.group(1))
        for p in paths:
            for q in (p, main_path(p), os.path.join(REPO, p)):
                if os.path.isfile(q):
                    sz = os.path.getsize(q)
                    if sz > BIG_FILE:
                        big.append(f"#{i}:{os.path.basename(q)}={sz // 1000}KB")
                    break
    M["big_reads"] = big
    M["image_reads"] = sum(1 for c in calls if c["name"] == "Read" and
                           re.search(r"\.(png|jpe?g|webp)$", c["input"].get("file_path", ""), re.I))
    # waits / polls
    M["sleeps"] = sum(1 for c in bash if re.search(r"\bsleep\s+\d", cmd(c)))
    M["monitors"] = sum(1 for c in calls if c["name"] == "Monitor")
    polls = sum(1 for c in bash if re.search(r"\b(status|tail -\d*|ls -l?t|pgrep|jobs|squeue|poll|log)\b", cmd(c))
                and len(cmd(c)) < 300)
    M["polls"] = polls
    # spend, handover, messages
    texts = [e[1] for e in P["events"] if e[0] == "say"] + \
            [c["input"].get("message", "") for c in calls if c["name"] == "SendMessage"]
    M["usd_mentions"] = sorted(set(m.group(0) for t_ in texts
                                   for m in re.finditer(r"(?<![\w{])\$\d+(?:\.\d{1,2})?\b", t_ or "")))[:12]
    M["messages_out"] = sum(1 for c in calls if c["name"] == "SendMessage")
    M["messages_in"] = sum(1 for e in P["events"] if e[0] == "in" and e[1] not in ("task",))
    M["handover_mentions"] = sum(1 for t_ in texts if re.search(r"hand ?over", t_ or "", re.I))
    return M


# ---------------------------------------------------------------- digest

def role_of(brief, meta):
    m = re.search(r"You are (?:the |a |an )?[\"']?([\w\- ]{2,40}?)[\"']? agent", brief)
    if m:
        return m.group(1).strip().lower().replace(" ", "-")
    return one(meta.get("description") or brief.split("\n")[0], 50)


def digest(P, M, meta, aid, level=0):
    W = [(260, 140, 320, 1500), (180, 110, 220, 1200), (140, 80, 160, 900), (110, 60, 0, 700)][level]
    cw, ow, sw, mw = W
    L = [f"AUDIT DIGEST {aid}  ({meta.get('description', '')})",
         f"start {M['start']}  end {M['end']}  wall {M['wall_h']} h  tool calls {M['tool_calls']}  "
         f"peak context {M['peak_ctx']:,}", "", "== BRIEF =="]
    b = P["brief"]
    L.append(b if len(b) < 9000 else b[:6000] + "\n[... brief cut ...]\n" + b[-2500:])
    L += ["", "== TIMELINE ==  (#n HH:MM tool: input -> ok|ERR [output])   << = inbound   >> = message out   .. = said"]
    marks = [100_000, 150_000, 200_000, 250_000, 300_000, 350_000, 400_000, 500_000]
    n, last_say = 0, None
    says = [i for i, e in enumerate(P["events"]) if e[0] == "say"]
    final_i = says[-1] if says else None
    for i, (kind, a, _b, t) in enumerate(P["events"]):
        hm = t.strftime("%H:%M") if t else "--:--"
        if kind == "ctx":
            while marks and a >= marks[0]:
                L.append(f"   -- context passed {marks.pop(0) // 1000}k tokens --")
        elif kind == "call":
            n += 1
            c = a
            res = "ERR " + one(c["out"], 150) if c["err"] else "ok"
            if not c["err"] and c["name"] in ("Bash", "Monitor", "Agent") and ow:
                s = snippet(c["out"] or "", ow)
                if s:
                    res += " [" + s + "]"
            L.append(f"#{n} {hm} {c['name'].replace('mcp__hifipushie__', 'hp.')}: "
                     f"{one(short_input(c['name'], c['input']), cw)} -> {res}")
            if c["name"] == "SendMessage":
                L.append(f"   >> TO {c['input'].get('to')}: {one(c['input'].get('message', ''), mw)}")
        elif kind == "in":
            w = 160 if a == "task" else mw
            L.append(f"   << {a.upper()} {hm}: {one(_b, w)}")
        elif kind == "say" and i != final_i and sw:
            L.append(f"   .. {one(a, sw)}")
    L += ["", "== FINAL REPORT ==", (P["events"][final_i][1][:5000] if final_i is not None else "(none)")]
    return "\n".join(L)


def build_digest(P, M, meta, aid):
    for level in range(4):
        d = digest(P, M, meta, aid, level)
        if len(d) <= DIGEST_BUDGET:
            return d
    # keep head and tail of the timeline
    lines = d.split("\n")
    i0 = next(k for k, l in enumerate(lines) if l.startswith("== TIMELINE"))
    i1 = next(k for k, l in enumerate(lines) if l.startswith("== FINAL REPORT"))
    tl = lines[i0 + 1:i1]
    keep = DIGEST_BUDGET - sum(len(l) + 1 for l in lines[:i0 + 1] + lines[i1:])
    head, tail, size = [], [], 0
    for a_, b_ in zip(tl, reversed(tl)):
        if size + len(a_) + len(b_) + 2 > keep:
            break
        head.append(a_); tail.append(b_); size += len(a_) + len(b_) + 2
    mid = len(tl) - len(head) - len(tail)
    return "\n".join(lines[:i0 + 1] + head + [f"[... {mid} timeline lines elided ...]"] + tail[::-1] + lines[i1:])


# ---------------------------------------------------------------- grade

def numbered(path):
    try:
        return "\n".join(f"{k}: {l}" for k, l in enumerate(open(path).read().splitlines(), 1))
    except OSError:
        return "(missing)"


def as_of(rel, when):
    """A repo file as it was at `when` (ISO time): the rules in force during the session."""
    try:
        rev = subprocess.run(["git", "-C", REPO, "rev-list", "-1", f"--before={when}", "main"], capture_output=True,
                             text=True).stdout.strip()
        r = subprocess.run(["git", "-C", REPO, "show", f"{rev}:{rel}"], capture_output=True, text=True)
        return (r.stdout, rev[:8]) if r.returncode == 0 else (None, "")
    except OSError:
        return None, ""


def rules_text(when):
    out = []
    for rel in PROCESS_GIT:
        txt, rev = as_of(rel, when)
        if txt is not None:
            out.append(f"### {rel} as of {rev} (in force at session start; line-numbered)\n" +
                       "\n".join(f"{k}: {l}" for k, l in enumerate(txt.splitlines(), 1)))
    for p in PROCESS_FILES:
        out.append(f"### {p} (line-numbered; ignore sections dated after the session)\n{numbered(p)}")
    for rel, pat in PROCESS_GREP:
        txt, rev = as_of(rel, when)
        if txt:
            hits = [f"{k}: {l}" for k, l in enumerate(txt.splitlines(), 1) if re.search(pat, l, re.I)]
            out.append(f"### {rel} as of {rev}, matching lines only\n" + "\n".join(hits[:12]))
    return "\n\n".join(out)


def grade(digest_text, M, out, model=None):
    rubric = open(RUBRIC).read()
    rules = rules_text(M["start"])
    prompt = (f"{rubric}\n\n## PROCESS FILES\n{rules}\n\n## OBJECTIVE METRICS (computed, trust these)\n"
              f"{json.dumps(M, indent=1)}\n\n## DIGEST\n{digest_text}\n\n"
              "Now return ONLY the JSON object described in the rubric.")
    cmd = ["claude", "-p", "--output-format", "json", "--no-session-persistence", "--tools", "",
           "--strict-mcp-config", "--setting-sources", "",
           "--system-prompt", "You are a strict, evidence-bound auditor of AI agent work sessions. Output JSON only."]
    if model:
        cmd += ["--model", model]
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=1500, cwd=out)
    open(os.path.join(out, "grade_raw.txt"), "w").write(r.stdout + ("\n[stderr]\n" + r.stderr if r.stderr else ""))
    env = json.loads(r.stdout)
    txt = env.get("result", "")
    u = env.get("usage") or {}
    usage = {"in": (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0) +
                   (u.get("cache_read_input_tokens") or 0), "out": u.get("output_tokens") or 0,
             "usd": round(env.get("total_cost_usd") or 0, 3)}
    a, b = txt.find("{"), txt.rfind("}")
    G = json.loads(txt[a:b + 1])
    return G, usage


def render_md(aid, role, M, G, usage):
    L = [f"# Audit {aid} ({role})", "",
         f"{M['start']} -> {M['end']} ({M['wall_h']} h), {M['tool_calls']} tool calls, peak context "
         f"{M['peak_ctx']:,}{' (OVER ' + str(CTX_LIMIT // 1000) + 'k)' if M['over_ctx_limit'] else ''}, "
         f"reviews {M['review_runs']} (verdicts PASS {M['pass']} / FAIL {M['fail']}), remote submits "
         f"{M['remote_submits']}, errors {M['errors']}, commits {M['commits']}.", ""]
    o = G.get("outcome", {})
    L += [f"**OUTCOME**: passed: {o.get('passed') or 'nothing'}; rounds per pass: {o.get('rounds_per_pass')}. "
          f"{o.get('verdict', '')}", ""]
    sc = [x["score"] for x in G.get("adherence", []) if isinstance(x.get("score"), (int, float))]
    L += [f"## A. Adherence (mean {sum(sc) / len(sc):.2f} / 2)" if sc else "## A. Adherence", "",
          "| item | score | evidence |", "|---|---|---|"]
    for x in G.get("adherence", []):
        L.append(f"| {x.get('item')} | {x.get('score')} | {one(x.get('evidence', ''), 400).replace('|', '/')} |")
    if G.get("claims"):
        L += ["", "### Final-report claims", ""]
        for x in G["claims"]:
            L.append(f"- **{x.get('status')}**: {x.get('claim')} — {one(x.get('evidence', ''), 300)}")
    for key, title, fix in (("process", "B. Process", "rewrite"), ("tooling", "C. Tooling", "change")):
        L += ["", f"## {title}", ""]
        for x in G.get(key, []):
            src = x.get("rule_source") or x.get("tool") or ""
            L.append(f"- **{x.get('finding')}** [{src}] ({x.get('severity', '')})\n  - evidence: "
                     f"{one(x.get('evidence', ''), 400)}\n  - {fix}: {one(x.get(fix, ''), 500)}")
    L += ["", "## Metrics", "", "```", json.dumps(M, indent=1), "```", "",
          f"grade call: {usage.get('in', 0):,} in / {usage.get('out', 0):,} out tokens, ${usage.get('usd', 0)}"]
    return "\n".join(L)


def write_index(row):
    os.makedirs(AUDITS, exist_ok=True)
    p = os.path.join(AUDITS, "index.tsv")
    rows = []
    if os.path.exists(p):
        rows = [l.rstrip("\n").split("\t") for l in open(p) if l.strip()][1:]
        rows = [r for r in rows if len(r) > 1 and r[1] != row["id"]]
    rows.append([str(row.get(c, "")) for c in INDEX_COLS])
    with open(p, "w") as f:
        f.write("\t".join(INDEX_COLS) + "\n")
        for r in rows:
            f.write("\t".join(r) + "\n")


def resolve(arg):
    if os.path.isfile(arg):
        return arg, re.sub(r"^agent-|\.jsonl$", "", os.path.basename(arg))
    aid = arg.removeprefix("agent-")
    return os.path.join(SUBAGENTS, f"agent-{aid}.jsonl"), aid


def run(arg, out=None, do_grade=True, model=None):
    path, aid = resolve(arg)
    out = out or os.path.join(AUDITS, aid)
    os.makedirs(out, exist_ok=True)
    meta_p = path[:-6] + ".meta.json"
    meta = json.load(open(meta_p)) if os.path.exists(meta_p) else {}
    P = parse(path)
    M = metrics(P)
    role = role_of(P["brief"], meta)
    M["role"] = role
    d = build_digest(P, M, meta, aid)
    M["digest_chars"] = len(d)
    open(os.path.join(out, "digest.txt"), "w").write(d)
    json.dump(M, open(os.path.join(out, "metrics.json"), "w"), indent=1)
    row = {"audited": dt.date.today().isoformat(), "id": aid, "role": role, "start": M["start"],
           "wall_h": M["wall_h"], "tool_calls": M["tool_calls"], "peak_ctx": M["peak_ctx"],
           "reviews": M["review_runs"], "pass": M["pass"], "fail": M["fail"],
           "rounds_to_pass": M["rounds_to_pass"] or "", "remote_submits": M["remote_submits"],
           "remote_over_12g": len(M["remote_over_12g"]), "errors": M["errors"],
           "repeat_fails": sum(M["repeat_fails"].values()), "commits": M["commits"],
           "git_add_all": len(M["git_add_all"]), "big_reads": len(M["big_reads"]), "polls": M["polls"]}
    if not do_grade:
        print(f"{out}/digest.txt ({len(d):,} chars)")
        return M, None
    G, usage = grade(d, M, out, model)
    sc = [x["score"] for x in G.get("adherence", []) if isinstance(x.get("score"), (int, float))]
    G["metrics"], G["role"], G["id"], G["grade_usage"] = M, role, aid, usage
    json.dump(G, open(os.path.join(out, "audit.json"), "w"), indent=1)
    open(os.path.join(out, "audit.md"), "w").write(render_md(aid, role, M, G, usage))
    row.update({"adherence_mean": round(sum(sc) / len(sc), 2) if sc else "", "n_process": len(G.get("process", [])),
                "n_tooling": len(G.get("tooling", [])), "grade_in_tok": usage["in"], "grade_out_tok": usage["out"],
                "grade_usd": usage["usd"], "verdict": one(G.get("outcome", {}).get("verdict", ""), 160).replace("\t", " ")})
    write_index(row)
    print(f"{out}/audit.md  adherence {row['adherence_mean']}  grade {usage['in']:,}+{usage['out']:,} tok ${usage['usd']}")
    return M, G


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__); sys.exit(2)
    out = model = None
    if "--out" in a:
        k = a.index("--out"); out = a[k + 1]; del a[k:k + 2]
    if "--model" in a:
        k = a.index("--model"); model = a[k + 1]; del a[k:k + 2]
    ng = "--no-grade" in a
    a = [x for x in a if x != "--no-grade"]
    run(a[0], out, not ng, model)
