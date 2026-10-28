# Trials: blind end-to-end runs, and how their lessons are kept

A trial is a fresh agent making a garment through the MCP only (no source, no shell), from a brief and references,
logging every step (trials/tN/log.md under /mnt/data/hifipushie). Joe's target (2026-10-27): **simple garments in ~3
design iterations, complex in ~10.** Progress is measured as iterations-to-pass on the same brief, not as the look alone.

## After every trial (the coordinator, before anything else)
1. Judge the result yourself beside the references (whole figure + the detail close-ups); send renders to Joe.
2. Count design versions and fits; give every round its CAUSE (the tool output or look that made the agent change it).
3. Triage each cause to ONE home, the narrowest that still enforces it:
   - **tool** (preferred): a default that is right first time, a gate that names the fix, a refusal with the next step.
     The agent needs no instruction.
   - **kind entry** (garment_kb.json kinds / details): facts true of one kind (a tee's crew neck, its short sleeve).
     Loaded only when that kind is drafted, so it can't leak into a jacket.
   - **guide**: a decision that needs judgement, with its reason (geometry or maps). Short.
   - **nowhere**: one-off, or a number tuned to this trial.
4. The over-specificity test, per lesson: would a pattern maker state it as a rule of the craft? ("a short sleeve hems
   at about its own width": yes; "set lean_deg 58": no, it is never written down.) Numbers come from the body
   (tapes, landmarks) or a kind's range, never from one trial's last value.
5. A lesson is LEARNED only after a transfer test: a different garment, or the same brief on a different body,
   takes fewer iterations too. Until then it is provisional (say so in the ledger row).
6. Add a row to the tracker below and a ledger row in codified.md.

## Iteration tracker

| Trial | Brief | Code | Design versions | Fits | Result (coordinator) | Main causes |
|---|---|---|---|---|---|---|
| t2 | hoodie, no reference | 2026-10-26 | 12 (stopped at fit) | - | stopped: wings, waist roll, shoulder | no hang, knit as woven, defaults |
| t3 | tee, no reference | threads hard | 23 | 7 | ~70 %, mock-turtle band | shirt neckline, folded band, defaults |
| t4 | tee + Joe's 2 refs | C235-C237 | 17 | 5 | ~80 % | defaults 4, truing 4-5, neck/shoulder coupling 2, length 2, blind neck 1-2 |
| t5 | same as t4 | C238 | 8 | 7 | ~75-80 % | blind neck 4, no default sleeve 1, worn_top advice 1, no-effect guess 1 |
| t6 | hoodie (t2's brief): TRANSFER test | C239 | 16 | 5 (+1) | ~65 %: hood, shoulder spikes | arg discovery 5, cap-ease band 3, no dropped-shoulder op 4, flush cuffs broke 2 (my bug), real fixes 4; threads gate stuck on folded cuffs (my bug) |
| t7 | white dress shirt, no reference: TRANSFER test | C239 | 17 (+9 alteration sets) | 5 | ~65 %: hem clings into the crotch, no shirttail | truing loop 8, shirttail unreachable 7, option names/units 5, gate thresholds 2, unmakeable default 1, real fixes 6 |

## Generalised lessons from t3-t7 (2026-10-27) and the fixes they call for
Each is a rule of the craft or of the tool contract, not of one garment. Fix home in brackets; [x] landed.

1. **Cloth hangs.** A garment falls from its supports (shoulders, waist) under its own weight; nothing is drawn onto the
   body except where it rests on it. Wings at the sides (hoodie, tee), sleeves standing off the arm (hoodie, tee), a hem
   clinging into the crotch (shirt) are the same missing hang. [fit: a hang step with hard threads; gates below]
2. **Early review measures how it hangs, not only that it is clean.** Hang gates in fit_garment, each naming the piece
   and the fix: side stand-off vs the ease (wings), sleeve axis vs the arm's and the gap under it, a step / spike where
   the cap meets the body, cloth drawn between the legs or into a hollow. A blind look runs without a reference against
   a short "how clothes hang" list. [x gates (C242: hang_reads, FAIL as the fit's until a hang step), x review_view no-reference]
3. **Targets are inputs.** Every measurable item of the brief (lengths, ease, shoulder position, neckline position, hem
   shape) is given as the target itself and the draft solves it; the gate measures the same item, so round 1 passes the
   measurable things by construction. One checklist per kind is the design input, the draft target, the gate row and
   the review item. [x lengths as body levels, sleeve levels; tool: per-kind checklist as input]
4. **The tool contract is strict.** An unknown key, op or option is an error naming the valid ones, with units and sign;
   an op a draft can't run is refused with the reason (never silently dropped); a failed call saves nothing; an option
   that replaces a default says so. (hoodie 5 rounds, shirt 5 + 7 on silent / crashing routes) [tool]
5. **Every draft comes out trued and its gates agree with its rules.** Seam ends square on any draft, made pieces and
   declared design corners excepted; a gate's target comes from the same rule the draft uses (stand height from the
   collar rule, shoulder from the declared drop, cap ease centred on what the solver reaches). (shirt truing 8, gate
   thresholds 2, hoodie cap band 3) [x knit drafts trued; x stand + cap ease from the rules (C242); tool: all drafts, shoulder from the drop]
6. **Shape is an op, not a hack.** A hem shape (shirttail, curved, high-low), a dropped shoulder, a corner rounded:
   one general op each, on any piece whatever drafted it; a third-party draft's own options (Simon hemStyle) work
   through the design table. (shirt 7, hoodie 4) [tool]
7. **A kind's defaults are makeable and right first time.** Every kind's defaults draft without error on the average
   bodies (a test); known faults are fixed in the kind entry (bust dart on a knit, short sleeve taper, tower placket on
   Simon). [x tee; test: every kind drafts]
8. **Geometry or maps is the artist's call, and both routes work for every band.** Flush leans only where the band lies
   on a slope (a neckband); a cuff or hem band is a cylinder. The thread gate holds a fold row to its crease allowance,
   as the fit does. (hoodie: flush cuffs broke; threads stuck at 17 %) [tool: my bugs]
9. **Look closely, and only compare like with like.** Close-ups of any region; a detail is never judged on a whole
   figure. [x focus, framing refusal]
10. **Lessons go to the narrowest home and are transfer-tested.** [x this page]
