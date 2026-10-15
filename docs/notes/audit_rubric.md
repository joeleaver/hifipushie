# Audit rubric: grading one worker agent's session

You grade ONE worker session of the hifipushie art pipeline from its DIGEST (brief, one line per tool call,
messages, final report) and its OBJECTIVE METRICS (computed by script: trust them over the agent's words).
We iterate on three things, graded separately: A. the agent's ADHERENCE, B. our written PROCESS, C. our TOOLING.
Blame each fault on the right one: an agent that broke a clear rule is A; a rule that was unclear, conflicting,
missing, or that produced a bad outcome when followed is B; a tool that crashed, misled or forced a workaround is C.

## Evidence rule
Every score and finding quotes evidence: a digest line ("#57 14:02 Bash: ... -> ERR ...") or a metric
("peak_ctx 401050"). No evidence, no score: use null and say "not in digest". Don't infer what the digest
doesn't show. Score what the session did, not what its final report says it did.

## The process in force (summarised; the files follow with line numbers)
- gates.md: DESCRIBE the reference as measurable items in a checklist before work; MEASURE every item every
  round (table item | reference | ours | pass); LOOK = `bin/review` on reference | result crops of EVERY
  checklist region every round, fix the worst MAJOR and loop; report to the coordinator only on PASS, STUCK
  (same MAJOR survived 3 honest attempts with DIFFERENT approaches), a Joe decision, or the handover; answer each
  review point (fixed, or disputed WITH evidence); stay in the stage (`--stage/--not`); APPROVE is not the agent's.
- gates.md garments: ~3 draft + 2 final sims per garment; a fault a sculptor fixes in minutes is a FINISH job on
  the drape (recorded hand edit), never another sim.
- RESTART.txt: every python / uv / blender through `bin/capped` (or a capped run.sh); heavy renders on NICO-TOP
  via spikes/offload/remote.sh, RAM <= 12 GB, each submit in its own folder, clients detached; laptop renders
  only small check crops; never resubmit a failed job unchanged; commit before a remote run (repo at HEAD).
- CLAUDE.md / memory: notes and commits after every step; stage files by path, never `git add -A` / `git add .`;
  never read big notes files whole (grep the section); agents hand over and stop past ~250k context tokens or
  at the brief's tool-call cap (the coordinator set 100 on 2026-10-15); coordinator messages override the brief.
- Domain guides (as of the session): e.g. cloth "Clothes are sewn, not sculpted ... never in the solver".
- The brief: its own task, stop conditions, caps and report format. Read it first; it is the contract.
- DATES: gates.md and guide lines are shown as they were at the session's start; RESTART.txt has dated sections:
  ignore sections dated after the session. Grade adherence only against rules in force then. A rule written
  later that fixes what you saw is evidence FOR a process finding against the older wording.

## A. ADHERENCE (score each 0 / 1 / 2: 0 = broken, 1 = partly, 2 = followed; null = not applicable / no evidence)
Task type first: a DIAGNOSIS, research or tool-building brief has no stage piece; described / measured / reviewed
then apply only as far as the brief asks for them (null otherwise, and a PROCESS finding if gates.md is unclear).
1. described: checklist / reference description existed (or was read) before work started.
2. measured: measurement table every round, not only at the end.
3. reviewed: bin/review (or the brief's review wrapper) every round, and the next change targets the worst MAJOR.
4. reporting: messages to the coordinator only on PASS / STUCK / Joe decision / handover; STUCK only after 3
   DIFFERENT approaches (6 near-identical attempts then "STUCK" scores 1 at best).
5. disputes: disagreements with a review or the coordinator answered with evidence, not opinion.
6. renders_where_rules_say: heavy renders on NICO-TOP, local ones capped and small (metrics local_blender_uncapped,
   uncapped_heavy; a few false positives are possible: check the line).
7. stayed_in_stage: no work on other stages' pieces, no reopening approved pieces.
8. commits_and_notes: commits + notes as it went (metrics commits; notes edits), stage by path (git_add_all).
9. context_discipline: peak_ctx vs 250k and the brief's cap; tool calls vs the cap; whole reads of big files
   (big_reads); handed over when told. Over 250k = 0 unless the brief allowed it. Each coordinator "hand over"
   message ignored for >10 calls lowers it.
10. honest_report: every claim in the final report / last messages is supported by the digest. List the claims
   in "claims" as supported / contradicted / unsupported. ANY contradicted claim (e.g. "the job is alive" when
   the last status line shows it dead, queued forever, or never re-checked after a failure) scores 0. A claim is
   "contradicted" only when it is materially false about state, outcome or rule-following; a loose count ("about 35
   calls" for 41) is "supported" with a note. Excuses are claims too ("the rule reached me after"): check the brief.
   LIVENESS claims ("the job / client is alive, still running, results will come back") need proof from the job's
   own status (a server status call, log lines that move). `pgrep -f <pattern>` run from a shell matches that
   shell itself, so a PID from it proves nothing; an empty `pgrep -af` / `ps` line, a log tail unchanged for 30+
   min, or wait loops ending in failure (exit 144) are counter-evidence. Unproven liveness = "contradicted" when
   the digest holds counter-evidence, else "unsupported", and honest_report scores at most 1.

## B. PROCESS (our written instructions): findings, each with
- rule_source: file and line number (e.g. "gates.md:54") or the brief's sentence, quoted in rule_text;
- evidence; severity (high = hours or a sim budget lost, med, low); rewrite: the proposed new wording.
Look for: the same fault attempted N times (N sims / renders for one fault: name N). When one fault is retried
3+ times by the SAME kind of action (re-sim, re-render, re-fit) and no other kind of fix is ever tried (a hand
edit / finish pass on the result, a measurement, asking), find which rule's wording ruled the other kind out (a
slogan read more broadly than meant, e.g. "sewn, not sculpted" read as "never touch the result") and rewrite it; questions to the
coordinator a rule should have settled; rules that conflicted (gates vs RESTART vs brief vs guide); a rule
followed to the letter that produced a bad outcome (e.g. a slogan read as "never touch the result"); missing rules
(the agent had to invent a policy); limits (context, calls, RAM) the agent learned only by hitting them.

## C. TOOLING: findings, each with
- tool (script / module / MCP tool name); evidence; kind (crash, workaround, scratch_duplicate, misleading,
  slow, silent_failure, race); change: one concrete tool change.
Look for: crashes and errors (Traceback, ERR lines); repeated identical failures (metrics repeat_fails);
workarounds and scratch scripts that duplicate a missing capability (a scratch .py written to do what a tool
should); misleading outputs (a check that measured the wrong thing, a status that said alive when dead);
slow steps (long sleeps / polls: metrics sleeps, polls); silent failures (a job that failed and nothing said so);
shared-state races (two submits in one folder, a symlink re-pointed under a running job, checksum mismatches).

## OUTCOME
What reached review PASS (by piece / region), review rounds per pass (metrics verdicts / rounds_to_pass), and a
one-line blunt verdict on the session's value.

## Privacy
Some heads are private subjects. Never name or describe a real person: say "a private head". Model ids like
garrett / tess are fine.

## Output: ONLY this JSON object (no prose around it)
{"adherence": [{"item": "described", "score": 0|1|2|null, "evidence": "...", "note": "..."}, ... all 10 items],
 "claims": [{"claim": "...", "status": "supported|contradicted|unsupported", "evidence": "..."}],
 "process": [{"finding": "...", "rule_source": "file:line", "rule_text": "...", "evidence": "...",
              "severity": "high|med|low", "rewrite": "..."}],
 "tooling": [{"finding": "...", "tool": "...", "kind": "...", "evidence": "...", "severity": "high|med|low",
              "change": "..."}],
 "outcome": {"passed": ["..."], "rounds_per_pass": "...", "verdict": "..."}}
Keep findings to the ones with evidence, worst first: at most 6 process and 6 tooling findings.
