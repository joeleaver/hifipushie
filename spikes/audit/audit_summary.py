#!/usr/bin/env python3
"""audit-summary: roll up /mnt/data/hifipushie/audits (index.tsv + each audit.json).

  audit-summary [--since YYYY-MM-DD] [--top N]

Per agent role (the brief's "You are the <role> agent", else the spawn description): sessions, mean adherence,
review rounds to the first PASS, tool calls per session, peak context. Then the top recurring PROCESS and TOOLING
findings, deduplicated by word overlap (same rule file / tool counts extra), ranked by sessions x severity.
"""
import json
import os
import re
import sys
from collections import defaultdict

AUDITS = "/mnt/data/hifipushie/audits"
SEV = {"high": 3, "med": 2, "medium": 2, "low": 1}
STOP = set("the a an and or of to in on for with from by is was are be it its that this as at not no into than "
           "then when each every one two per via our their they them only also out after before".split())


def words(s):
    return {w for w in re.findall(r"[a-z0-9_.]{3,}", (s or "").lower()) if w not in STOP}


def role_key(r):
    r = re.sub(r"\(.*?\)", "", r or "").strip().lower()
    return re.sub(r"[\s_]+", "-", r) or "?"


# Recurring themes: a finding matching one joins that theme's cluster (first match wins); others cluster by words.
TOPICS = [
    ("context / call cap", r"context|250k|tool[- ]call cap|100[- ]call|call cap|token (limit|count)"),
    ("remote RAM over slot", r"\b(1[3-9]|2\d) ?GB|ram[_ -]?gb|slot cap|over[- ]cap|larger than any"),
    ("shared submit folder", r"symlink|repo\.tar|same folder|own folder|sha256"),
    ("self-matching pkill / pgrep", r"pkill|pgrep"),
    ("job wait / status", r"wait[- ]loop|poll|until[- ]loop|600 ?s|no (blocking )?wait|status command|job-wait"),
    ("same fault retried by re-sim", r"re-?sim|sims? (budget|far exceed)|same kind of action|finish(ing)? (pass|job)|hand edit"),
    ("LOOK / review cadence", r"\breview\b.*(every round|only once|skipped|single)|LOOK step|blind review"),
    ("render placement laptop vs NICO-TOP", r"laptop|NICO-TOP by default|light check|5 s"),
    ("worktree command guard", r"isolation guard|too complex|compound shell|heredoc"),
    ("checklist measure tool", r"measure(ment)? (table|tool)|scratch (measurement )?scripts?|checklist-measure"),
]


def topic(it):
    t = it.get("finding", "")
    for name, pat in TOPICS:
        if re.search(pat, t, re.I):
            return name
    return None


def cluster(items, key_src):
    """By theme (TOPICS), else greedy Jaccard >= 0.28 on finding words (+0.1 if the same source)."""
    cl = []
    for it in items:
        w = words(it["finding"] + " " + it.get("change", it.get("rewrite", "")))
        src = (it.get(key_src) or "").split(":")[0].strip().lower()
        tp = topic(it)
        if tp:
            c = next((c for c in cl if c.get("topic") == tp), None)
            if c:
                c["items"].append(it); c["ids"].add(it["_id"]); continue
            cl.append({"w": w, "src": src, "items": [it], "ids": {it["_id"]}, "topic": tp}); continue
        best, bs = None, 0
        for c in cl:
            if c.get("topic"):
                continue
            j = len(w & c["w"]) / max(1, len(w | c["w"])) + (0.1 if src and src == c["src"] else 0)
            if j > bs:
                best, bs = c, j
        if best and bs >= 0.28:
            best["items"].append(it); best["w"] |= w; best["ids"].add(it["_id"])
        else:
            cl.append({"w": w, "src": src, "items": [it], "ids": {it["_id"]}})
    for c in cl:
        c["score"] = len(c["ids"]) * 10 + sum(SEV.get(str(i.get("severity", "")).lower(), 1) for i in c["items"])
        c["rep"] = max(c["items"], key=lambda i: SEV.get(str(i.get("severity", "")).lower(), 1))
    return sorted(cl, key=lambda c: -c["score"])


def main(argv):
    since, top = "", 5
    if "--since" in argv:
        since = argv[argv.index("--since") + 1]
    if "--top" in argv:
        top = int(argv[argv.index("--top") + 1])
    p = os.path.join(AUDITS, "index.tsv")
    lines = [l.rstrip("\n").split("\t") for l in open(p) if l.strip()]
    cols, rows = lines[0], [dict(zip(lines[0], r)) for r in lines[1:]]
    rows = [r for r in rows if (r.get("start") or r.get("audited", ""))[:10] >= since]
    by = defaultdict(list)
    proc, tool = [], []
    for r in rows:
        by[role_key(r["role"])].append(r)
        try:
            G = json.load(open(os.path.join(AUDITS, r["id"], "audit.json")))
        except OSError:
            continue
        for x in G.get("process", []):
            proc.append(dict(x, _id=r["id"]))
        for x in G.get("tooling", []):
            tool.append(dict(x, _id=r["id"]))
    f = lambda v: float(v) if v not in ("", None) else None
    mean = lambda xs: (sum(xs) / len(xs)) if xs else None
    out = [f"# Audit rollup ({len(rows)} sessions{', since ' + since if since else ''})", "",
           "| role | sessions | adherence /2 | rounds to PASS | tool calls / session | peak ctx (mean / max) |",
           "|---|---|---|---|---|---|"]
    for role, rs in sorted(by.items()):
        ad = [f(r["adherence_mean"]) for r in rs if f(r.get("adherence_mean")) is not None]
        rp = [f(r["rounds_to_pass"]) for r in rs if f(r.get("rounds_to_pass")) is not None]
        tc = [f(r["tool_calls"]) for r in rs]
        pk = [f(r["peak_ctx"]) for r in rs]
        out.append(f"| {role} | {len(rs)} | {mean(ad):.2f} |" if ad else f"| {role} | {len(rs)} | - |")
        out[-1] += (f" {mean(rp):.1f} |" if rp else " no PASS |") + f" {mean(tc):.0f} | " \
                   f"{mean(pk) / 1000:.0f}k / {max(pk) / 1000:.0f}k |"
    for title, items, src, fix in (("PROCESS", proc, "rule_source", "rewrite"), ("TOOLING", tool, "tool", "change")):
        out += ["", f"## Top {top} {title} findings (sessions: ids)", ""]
        for k, c in enumerate(cluster(items, src)[:top], 1):
            r = c["rep"]
            out.append(f"{k}. {('[' + c['topic'] + '] ') if c.get('topic') else ''}**{r['finding']}** [{r.get(src, '')}] ({len(c['ids'])} sessions: "
                       f"{', '.join(sorted(i[:7] for i in c['ids']))})\n   - {fix}: {r.get(fix, '')}")
    print("\n".join(out))


if __name__ == "__main__":
    if "-h" in sys.argv or "--help" in sys.argv:
        print(__doc__); sys.exit(0)
    main(sys.argv[1:])
