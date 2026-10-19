# STATE: codify (durable lessons into the repo) -- rewritten 2026-10-19, session 1. Nothing in flight.

## Current best
- docs/notes/codified.md: THE LEDGER, one row per durable lesson (P process, R repo / machine, H head, S skin, A hair,
  C clothes, E expressions / export / rig, X style / other) with where it is codified and its status.
- docs/notes/character_recipe.md: the stage-order recipe for a new realistic game character (<= 250 lines).
- docs/notes/traps.md: symptom -> real cause -> what to check first.
- CLAUDE.md "Start here" points new characters at the recipe + traps.

## Open items (by impact on the next character)
1. CHECK-PLANNED rows: another agent is turning them into checks; the coordinator flips each row's status when one
   lands (cite the function / test, grep it first).
2. ENFORCED-BRANCH: the approved-head export gate (asset.approved_head) and FOLD_FORM_MAX_MM live only on
   worktree-agent-ad0815704f43e0e00 / worktree-agent-a369eb41a63e51a4a, not main. Merge them, then mark ENFORCED.
3. Hair budget unit contradiction (ledger A8): memory says the role default counts card faces and drawn must fit the
   range max; code (hair.py cards fit, `bf_`) and both hair STATE pages fit DRAWN to the default. Coordinator decides.
4. `hair_clumps.FILL` (bake packing share) is set to 1.0 by Tess RC rc2n's HP_FS_SET and hair-cards r45a's hk.FILL=1,
   apparently meant as the crown fill (ARCH_FILL, default 1 already). Check what it did; rename to BAKE_FILL.
5. Smile mix A2 lives only in /mnt/data/hifipushie/happy/NOTES.md: copy it into a faceshapes preset table.
6. bin/ guards (review exit 4, review-ab, approve, capped) are outside the repo, unversioned (ledger P14).

## Decisions in force
- Statuses: ENFORCED only when the code refuses / a test fails, verified by grep; a default or warning is DOC.
- No private-head names, codes or relations in any of these files; refer to "private heads".
- New lesson: a row the same day (check if possible, else default, else recipe / traps line).

## Dead ends
- (none yet)

## Commands
- Verify a claim: `grep -n <name> src/hifipushie/*.py tests/*.py`; on a branch: `git grep -n <name> <branch> -- src tests`.
- Size: `wc -c CLAUDE.md` (< 8192); `wc -l docs/state/*.md` (<= 60 each).

## History
- Commits 66a5aedb (ledger), 8c251f0c (traps), ae1295c3 (recipe), then this page + the CLAUDE.md "Start here" line.
NEXT: coordinator reconciles CHECK-PLANNED rows as checks land; resolve items 2-5.
