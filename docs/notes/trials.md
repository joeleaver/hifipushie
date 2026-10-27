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
| t6 | hoodie (t2's brief): TRANSFER test | C239 | | | | |
