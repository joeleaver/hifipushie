# Session audits: grading worker agents (2026-10-15, "audit" agent)

Joe: "you'll need some way of grading how well they're following the instructions and how well the instructions
work." We iterate on three things, graded apart: the TOOLING, the PROCESS we write down, and the agents' ADHERENCE.

## Tools
- `/mnt/data/hifipushie/bin/audit <agent-id | transcript.jsonl> [--out DIR] [--no-grade] [--model M]`
  (code `spikes/audit/audit.py`). Writes `DIR` (default `/mnt/data/hifipushie/audits/<id>/`): `digest.txt`,
  `metrics.json`, `audit.json`, `audit.md`, `grade_raw.txt`; one row per id in `audits/index.tsv` (a re-audit
  replaces the id's row).
- `/mnt/data/hifipushie/bin/audit-summary [--since DATE] [--top N]` (code `spikes/audit/audit_summary.py`):
  per role (from the brief's "You are the <role> agent"), mean adherence, review rounds to the first PASS, tool
  calls, peak context; top recurring PROCESS / TOOLING findings, merged by theme (`TOPICS`) then word overlap.
- Rubric: `docs/notes/audit_rubric.md` (sent with every grade). Test: `tests/test_audit.py` (synthetic transcript,
  no LLM).
- Audits and digests name private subjects: they stay in /mnt/data, never in git. The rubric tells the grader
  to say "a private head".

## How it works
1. DIGEST, no LLM. Transcript rows: the first user string is the brief; `assistant.tool_use` / `user.tool_result`
   pair by id (`is_error`); coordinator messages are `attachment.queued_command` with `origin.kind == "coordinator"`
   (task notifications are the same type, with `<task-notification>`); context = input + cache_read +
   cache_creation tokens per assistant message (deduped by message id). One line per call: tool, input (heredoc
   bodies replaced by `<<EOF [n lines]`, so the command that RUNS is visible), ok / ERR + 150 chars, and for Bash a
   "notable" output line (VERDICT, Traceback, queued, alive...). Markers when context passes 100k, 150k...
   Shrinks in 4 levels to fit ~95k chars, then elides the timeline's middle. Calibration digests: 20-76k chars.
2. METRICS: tool calls by tool, peak context (> 250k flagged), wall time, review runs (bin/review or a `rev*.sh`
   wrapper) and verdicts (line-anchored `VERDICT: PASS|FAIL`: the review script's help text has the phrase
   in quotes and was counted as a PASS once), remote submits and RAM > 12 GB, local Blender runs (`blender -b /
   --python / x.blend`) capped or not (capped, bin/slot, run.sh / q.sh count as wrapped), uncapped `uv run x.py`,
   errors, repeated failing calls, commits, `git add -A/.`, whole reads of text files > 40 KB, image reads,
   sleeps / Monitors / polls, `$` mentions in the agent's own words.
3. GRADE: ONE `claude -p --tools "" --strict-mcp-config --setting-sources "" --system-prompt ...` call, prompt on
   stdin: rubric + gates.md AS OF the session's start (`git rev-list -1 --before=<start> main`) + RESTART.txt
   (dated sections; told to ignore later ones) + the guide_spec.md cloth lines as of the start + metrics + digest.
   It returns JSON (adherence 10 items 0-2 with evidence, claims, process, tooling, outcome); audit.md is
   rendered from it. 20-51k tokens in, ~10k out, $0.31-0.60 per session (Opus).
   - A bare `claude -p` loads the user's whole setup (CLAUDE.md, memory, MCP instructions): 210k tokens and
     $1.69 to answer "say ok". The flags above cut that to 0.7k. bin/review calls claude without them, so
     every blind review pays that ~210k overhead (TOOLING card owed).

## Calibration (2026-10-15, 7 sessions + the lashes session)
Scores after the rubric changes below (adherence mean / 2; P = process, T = tooling findings).

| session | role | calls | peak ctx | adherence | what the grader said |
|---|---|---|---|---|---|
| a80c0a0 | skin | 99 | 186k | 1.90 | best adherence; 1.1 h spent waiting on the NICO-TOP queue; review loop assumes ~1 min turns (P high) |
| ad36de0 | garrett-eyes (good) | 41 | 165k | 1.44 | good diagnosis; 13 ~46 s lit renders local + 2 uncapped Blender runs; "the rule reached me after" excuse contradicted by the brief |
| a7da231 | mouth-eye-bias | 205 | 362k | 1.22 | context 0; brief too big for 250k / 100 calls (P high); ~15 variants judged by numbers, one review at the end |
| aca0b1a | jaw-control | 239 | 401k | 0.90 | context 0; ~135 calls past 250k; claims of tests / rebuilds unsupported; remeasure.py deleted-file dependency (T high) |
| ab552c1 | hair-garrett | 119 | 197k | 1.00 | dead-client claim CONTRADICTED (honest 0); remote.sh repo.tar.gz race (T high); 20 GB request blocked queue (T high); no review in 15 rounds |
| a275cc2 | dress-tess | 189 | 265k | 1.30 | neckband retried 6x by re-draft + re-sim, never a hand finish (P high, guide_spec.md:111,117 "sewn, not sculpted"); checklist vs review conflict |
| a0d609f | dress-garrett | 131 | 238k | 0.88 | no measurement table; 3 sims, 2 failed with no cause; mirror_mesh silently ignored (T high); "stopping at ~90 calls" contradicted |
| ac02119 | lashes | 264 | 362k | 0.90 | context 0; 24 GB / 20 GB submits (metric remote_over_12g); RAM rules conflict (RESTART.txt:5 vs :30, P high) |

Known truths (from the coordinator's own reading) and whether the grader surfaced them:
- Contexts far over the limit: CAUGHT from round 1 (context_discipline 0 in the four sessions over 250k, plus
  dress-garrett on its brief's 200k trigger).
- The dead-client claim (hair-garrett): MISSED in round 1 (honest_report 2): the digest showed `pgrep -f ...
  -> 2691344`, which the grader took as proof. pgrep -f from a shell matches the shell itself. CAUGHT after the
  LIVENESS rule: "contradicted", citing the log stuck at "queued" for 75 min, two wait loops dying with exit 144
  and the self-matching pgrep.
- The neckband loop of 6 sims: round 1 found "sims far exceed the budget" but cited the FINISH rule from
  gates.md:84-87, which landed at 23:06 UTC, after the session. With rules as of the session's start and the
  "same kind of action" rule it names the old slogan (guide_spec.md:111 "Clothes are sewn, not sculpted", :117
  "never in the solver") as what ruled out a hand finish. CAUGHT.
- remote.sh shared-folder repo.tar.gz race: CAUGHT both rounds (TOOLING high, hair-garrett).
- The 20 GB offload that blocked NICO-TOP: CAUGHT both rounds (metric remote_over_12g on the lashes session,
  TOOLING high in lashes and hair-garrett, PROCESS "RAM rules conflict").

## Rubric / code changes from calibration
1. Line-anchored VERDICT count (the grader itself flagged a PASS counted from bin/review's help text).
2. Heredoc bodies stripped before matching commands and in the digest (round 1 flagged `grep ... blender_game.py`
   as a Blender run; the grader couldn't see the real `blender -b` call after a heredoc).
3. Process files as of the session's start; RESTART sections after the session ignored.
4. LIVENESS claims need the job's own status; pgrep -f self-match noted.
5. Loose counts ("about 35 calls" for 41) are not contradictions; excuses are claims.
6. "Same fault, same kind of action 3+ times" -> find the rule that ruled the other kind out.
7. Task type: diagnosis / research / tool-building briefs score described / measured / reviewed only as far as
   the brief asks (the good eyes session went 1.11 -> 1.44; it still loses points for local renders and the excuse).
8. Rollup merges findings by theme first (`TOPICS` in audit_summary.py): word overlap alone kept the 20 GB
   queue finding from two sessions apart.

## What it catches / misses (judgement)
- Catches: limits overrun (numbers), rule-breaking by command shape (uncapped Blender, > 12 GB submits,
  git add -A), loops (same fault, N attempts), false claims IF the digest holds counter-evidence, tool crashes
  and races with a clear error line.
- Misses / weak: anything only visible in images (it never sees the renders: art quality is bin/review's job);
  claims about numbers the agent computed (mostly "unsupported", not checkable); silent waste between calls
  (a job running fine but pointless); harness errors are reported as TOOLING though they aren't ours (worktree
  command guard); the evidence is one grader's reading: scores move ~0.1-0.3 between runs of the same digest.
- Cost of calibration: 18 grade calls, 638k tokens in / 176k out, about $8.6, plus one $1.69 probe of a bare
  claude -p.

STATE: bin/audit + bin/audit-summary working; 8 sessions audited (/mnt/data/hifipushie/audits, summary.md).
NEXT: run audits on each finished session (the coordinator, after each handover); fix bin/review's claude
flags; take the top rollup findings to the gates / RESTART owners.
