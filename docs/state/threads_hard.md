# STATE: threads hard (no cloth stretches in the fit past its cap) -- 2026-10-26

GOAL (Joe 2026-10-26: "why are we allowing it [to stretch]?"; then "rebuild"): thread STRETCH is a hard rule in every
fit; a pattern that can't reach shows as what it can't reach (threads past cap where contact wins, cloth inside, open
seams, neck points short), named by piece. Ledger C235.
DESIGN (rebuilt, branch threads-hard, default on, env PF_THREADS_HARD=0 for A/B): each relax round the existing solve
PREDICTS (all soft goals: bending, folds / ARAP cells, attraction, pins, flap targets, layer pressure); then
pattern_form._hard_pass PROJECTS the hard constraints together, Gauss-Seidel, to convergence on the phase's last round
and at the end of assemble: threads (_thread_limit by colour, woven shear lock), the seams THIS phase sews (hp_; a band
not yet stood up is not sewn) + closures, contact planes from hard_planes(Xn) (form d>=0, layer under / over, LAYER_GAP),
contact LAST (misfit -> over_cap_by_piece, C172 holds). Only STRETCH is hard (THREAD_SQUEEZE 1.0; shortening is the
solve's: capped both ways the loop cycled with contact); stiff pieces (cells / interfaced) shorten <= cap except on fold
rows. HARD_CELLS False (made pieces / folds / flaps keep their own rests; in: sprung fall rippled 130 mm), HARD_FLAP_PLANES
False (pushed every collar thread to the cap). Reports: over_cap_by_piece, inside_by_piece, neck_point_mm; next_steps
misfit_lines; fit_garment gates threads past cap p99 <= 1 %; face_threads reads stretch only.
TESTS ($T=/mnt/data/hifipushie/threads; $T/pf_r2.log): pattern_form + fold_checks + mcp_rules + garment_reads: 7 fail.
- KATs whose old answer NEEDED stretch (measured on the soft fit): plumb hold (threads p99 14.2 %, max 25) x2 tests;
  sprung fall turned 166.8 of 170 (soft fall p99 4.8 %, max 7.5); straight collar asserts EDGE strain p99 < 10 (an
  unsprung fall's edge needs ~4.7 %; its geometry is exact now: 27.0 / 12.9 mm, 176 deg). RESTATE each per C235: threads
  <= cap + the misfit reported (over_cap / gap), keep the shape asserts the cut allows; record the soft numbers.
- REAL faults to fix: nested collars through each other (bodice 12, stand 12, fall 8 vertices; flap-on-base is soft
  now); fold_checks two-piece collar fold_on_base FAIL (same); fold running off mid-length 25.2 vs < 25 deg (marginal).
- Still untested on this design: the rest of the suite (old env leak fixed in tests/test_artist.py), hoodie / jacket /
  shirt readouts ($T/ab.py <model> <garment> <tag>, $T/where.py), timing (the old final-pass version ran 3.5x slower).
OPEN: made pieces' stretch is still soft (ARAP cells; HARD_CELLS off). Collars cut without spring can't turn flat at 2 %.
Scratch A/B scripts: $T/kat.py <test names>, cellab.py, plumbab.py, planeab.py, fallthreads.py.
NEXT: restate the 4 stretch-dependent KATs; fix nested-collar layering (flap planes as a softer hard? or made-on-made
floor); full suite exit 0; hoodie / jacket / shirt readouts; then a FRESH agent makes a T-shirt through the MCP on this
branch (Joe 2026-10-26); judge its full figure myself before sending.
