# STATE: dress-tess -- rewritten 2026-10-19 after session 18 (2026-10-18). Nothing in flight.

## Current best (frozen for export)
- **/mnt/data/hifipushie/dress_tess/frozen/2026-10-18_s18/{coat,sweater,jeans}.pkl** (cloth.freeze, FULL results, model dt_tess v112):
  coat key 59dd2d0143597d57 (+ sculpt_J24: wearer's-left front's lower part = the approved right front's mirror, faded up the
  chest z 1.0 -> 1.12 and 240 mm toward the side seam; woven crush detail 0.00056 m, seam_line 0.1), sweater ac35eb1dfaa337db,
  jeans 3e42fc7c870b3383. Props unchanged. Crossings = the pre-existing 19 (all on the right side, z 1.14-1.18).
- The Tess export (rc2n, rc2t) already ships this s18 freeze (docs/state/tess_export.md in the assembly worktree).
- Not ready for Joe as a whole outfit until the export's game render confirms the fronts.

## Open faults (by game visibility)
1. 1 m (front): possible grey strip at the coat opening = the front's inside facing the camera; mostly gone with J. Re-check in the
   assembly's game render; if left: a facing that reads as the outer cloth (export_part inner shell normal rolled at the front
   edge), tested on the game render.
2. 1 m: coat surface clean but flatter than the concept's soft swirling folds: next lever = lower-frequency, lower-contrast fold
   relief (not more crush), judged in the game render.
3. 1 m: pocket / lapel rims, side-seam bead; smooth 10 mm faces.
4. 3 m (back): the 9 back crossings; the 19 right-side crossings (pre-existing).
Fixed: left front kink over CF (hand finish J), coat diamond / lattice smears (crush 1.6 -> 0.56 mm), sweater folds under the coat 2 -> 0.

## Decisions in force
- Joe reopened the wearer's left front (2026-10-18): finished by hand as the right front's mirror (solve is the base, the agent finishes).
- Coat surface detail is judged in the GAME render (supersedes stage tiles); adopt by blind review (bin/review after 13:00 MT,
  else a fresh subagent with the concept crop as reference).
- Rented re-sims OK'd ($5/day via oxidegen), ONE per proven fix: prove locally first. Construction before solver.
- Spike gate must PASS before sheets (rr/s17/spike.log pattern).

## Dead ends (don't retry)
- "Left front caught under the sweater hem" as the cause (s17): disproved (start 11.8 mm clear, no edge crosses a sealed hem;
  it rests outside on the sweater's belly: a chaotic hang). seal_under (cloth.seal_rims) stays an opt-in tool, unused.
- Woven crush 1.6 mm (criss-cross streaks) / 0.8 mm (lattice lines) / 0.3 mm (flat).
- Rewriting a sculpt file under the same name: served from the in-process cache; the file name is its identity (write anew).
- s17's "behind the sweater" counts (normal sign flips below the hem).

## Commands (G=/mnt/data/hifipushie/dress_tess)
- Scripts run via `TAG=<s> bash $G/run.sh <script>` (env + capped). Session scripts in $G/rr/s18/.
- Hand finish: rr/s18/mirfront2.py (sculpt offset keyed on the sim), check through the cached pipeline: rr/s18/mirck.py.
- Coat maps as the export writes them: rr/s18/bake_nm.py; game-render swap test: rr/s18/gsw.sh (assembly game check, rc2c LOD0).
- Rims / collider: rr/s18/rims.py, sealck.py. Tests: test_seams, test_cloth, test_cloth_layers.

## History (grep only)
docs/notes/cloth.md "### dress-tess session 17" / "session 18" and their Handovers; "FROZEN FOR EXPORT" lines.
