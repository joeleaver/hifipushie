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
DEFAULTS now: HARD_CELLS True (made pieces / folds / flaps IN the loop: out, they absorbed every misfit on real
garments: shirt stand p99 534 %, jacket fronts 40 %), STIFF_SQUEEZE False, CREASE_CAP 0.25 (fold-row triangles: the
outer layer of a fold is longer). READOUTS r5 ($T/readouts_r4.log + task logs): shirt sleeves / cuffs / back <= 3 %,
yoke 6.7, front.L 12 (max 53); inside 6 (soft 113). Jacket sides / sleeves ~2 %, inside 0, seams 0.2 mm, neck points
11-17 mm short. Collar / lapel p99 ~25 % = crease rows at CREASE_CAP (where.py counts them as cloth: read them apart).
Hoodie not re-run on r5. Shirt 157 s, jacket 730 s.
TESTS ($T/pf_r5.log): cloth files 3 fail, NOT loosened further: fold run-off 26.5 (< 26, soft 23.9), sprung fall ripple
16.9 mm (< 15), fold_checks two-piece fold_on_base share 0.107 (< 0.02: the fall through its stand). Nested collars and
the straight collar pass. Restated (needed stretch on the soft fit): plumb hold x2 (14.2 %), sprung fall turn 165
(4.8 %), collars' edge strain, tight tube (16 % short), fold run-off 26. Suite (with HIFIPUSHIE_ASSETS set: the repo's
convention, else test modules' HOME leaks break asset lookup): only cloth + unrelated eyedetail / skin noise / rented
sims gate / terrain fixture 'T' errors (untouched code; not re-run on main).
OPEN: a fall sinks through its stand (fold_on_base); flap-on-base planes (HARD_FLAP_PLANES) fixed it but broke the straight collar while cells were out: re-test with cells in. Collars cut without spring can't turn flat at 2 %.
Scratch A/B scripts: $T/kat.py <test names>, cellab.py, plumbab.py, planeab.py, fallthreads.py.
T-SHIRT TRIAL t3 (2026-10-27, fresh headless claude in this checkout, MCP only; /mnt/data/hifipushie/trials/t3/log.md,
fit_v23_*.png): ~85 tool calls, reads as a tee (~70 %): threads p99 2.8 %, misfit "nothing", none inside. Faults: neckband
stands up like a mock-turtle; boxy, hem flares, sleeves stand off (no gravity on the form); the diag strain map still
paints EDGE strain (bias shear red / blue) while the gate reads threads. The misfit report never had to fire (a tee
fits within its threads). Its tool gaps: style push KeyError 'rounds', contour op crash, collar band ratio ignored
under options (works under generate.ratio), worn_top channels knit side seams, no close-up of the fit, renders' names
not printed.
NECK + MAP (C236, 2026-10-27): diag strain map = threads past cap; tee neckline "crew" (band edge on the neck base,
seam a band width out, neck pins moved out with it); knit bands rest at their sewn length. Trial tee refit
(workspace trial_tshirt_t3d = t3 v23 minus its own neckline op): reads as a crew neck; OPEN the band is a thick round
roll standing off the neck at the sides. Renders /mnt/data/hifipushie/neckband/ab_clay*.png, crew2_neck.png.
BAND (C237, 2026-10-27): folded bands sew both raw edges (BUILD 18); generate represent "flush" (one leaning layer,
fold in the maps) is the agent's call; trial tee t3d with a flush band reads like Joe's reference (ref_vs_flush.png);
its neckline opening still a little high / narrow. OPEN: pressing a narrow fold flat as geometry (collars, cuffs).
NEXT: a fresh agent makes the tee end to end on this code (crew neck + flush band are the tee kind's defaults? flush is
NOT a default: the agent chooses); the 3 open fold tests; the flat-fold capability.
