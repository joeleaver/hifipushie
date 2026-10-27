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
TESTS (87a5a5ba +): cloth files ($T/pf_r3.log) 2 fail, both MADE PIECES layering: nested collars 4-5 bodice + 2-4 stand
vertices through the inner (2 fixes failed: made-on-made plane, re-linearised planes), fold_checks two-piece collar
fold_on_base share 0.033 (< 0.02). HARD_FLAP_PLANES on fixes fold_on_base but breaks the straight collar (stand 19 / 27)
and nested (19/10/7): off. Restated (needed stretch on the soft fit): plumb hold x2 (14.2 %), sprung fall (4.8 %),
collars' edge strain, tight tube (16 % short; layer under now hard in every fit), fold run-off 26 deg (25.2 vs 23.9).
OPEN: made pieces (collars, bands) are outside the hard loop: their stretch is soft (straight collar threads p99 5.2 %, max 58 at the crease) and their layering is the 2 failing tests; in the loop they rippled (HARD_CELLS). Collars cut without spring can't turn flat at 2 %.
Scratch A/B scripts: $T/kat.py <test names>, cellab.py, plumbab.py, planeab.py, fallthreads.py.
NEXT: full suite ($T/suite2.log); hoodie / jacket / shirt readouts; T-shirt trial (a T-shirt has no made pieces: the open item doesn't block it). Then made pieces in the loop with their own folded rest as the thread frame.
