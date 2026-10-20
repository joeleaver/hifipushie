# STATE: dress_garrett_fit (Garrett jacket + shirt: closed form fit + ONE release sim + arrangement) -- 2026-10-20, round 21

STATE: round 21 step 1 done: the closed form fit's fronts no longer pass through each other (pattern_form.LAP_LAYER,
default on, KAT). r21c = r19a + LAP_LAYER: jacket front|front crossing 147 -> 0, shirt 398 -> 0 (over = front.L, the
wearer's left, men's left over right). Cost: jacket stretch p99 8.4 -> 18.2 % (front.R NECK 0-100 mm below HPS + the
break's X point). Lapel check (Joe on r20k): the wearer's RIGHT lapel (front.R, camera left) goes through ITS OWN base at
50-100 mm below HPS, 21-28 mm off the roll line, made in the closed fit (r19a 6.6 % FAIL, r19w 10.7 %, r20k 5.9 %);
r21c 3.1 % PASS but still 4.5 mm deep there. Nothing approved.
Waist measured: draft = book (786 x 1.14 = 896), the form keeps it (r21c 905), but the SHIRT is 895 at the waist
(+109, a stiff 17 mm tube): the jacket lies 1-11 mm over it and clings. Release+arrange on r21c (r21k): CCD fails at
t = 0 (preflight self False, strain 6.6 %): no arranged r21, no reviews. Spend $0.
NEXT: (0) r21k's CCD fail at t = 0: the 1.5 mm lap gap vs ZOZO's contact gap (try LAP_GAP = the release's contact
gap, 2-3 mm, on the KAT first) and the layering's start strain. (1) the WAIST: press the shirt's fullness under the
jacket at the waist (layered_fit outer_first / TWO LAYERS), gate row: jacket waist over the body >= 10 % and over the
shirt >= the book minimum; then the side pinch. (2) front.R's neck stretch on r21c (why the layering moved it).
(3) release + arrangement (round 20's r20k setup: g20.py arrange=1 keep=1 pull=100) on the layered + eased
fit: no_front_through_front PASS, lapels roll to the break, hem without crumpling. (4) neck openings: release the neck
hold after the sew phase (hold_ring CCD-failed at t = 0). (5) table + renders + 3 blind reviews ("worn open").

## Method (Joe 2026-10-20)
Open jacket = the BUTTONED fit on the dress form (pattern_form.assemble, top button fastened), then ONE short release
sim (cloth_release, MCP release_garment; docs/state/cloth_release.md), then ARRANGED (MCP arrange_garment: soft pins
moved to the concept's edge rows, settled, kept or let go, springback reported). The concept's opening (edge off CF
71/78/94 at 450/550/650, break x 64, V width 237) is reached by arranging, never by fit levers or the pattern.

## Candidates (nothing approved)
- Fit r21c ($FR21/fitcheck.sh r21c: r19a's recipe CLOSED=1 LAPEL_W=0.081 ROLL_R=0.006 ROLL_GAP STAND_RUN_OFF on,
  traced) -> $FR21/asm_r21c.pkl. Round 19/20: r19a fit, r19w release+weld, r20k arranged ($FR20/asm_r20k.pkl).

## Table (concept | r15e fit | r19w release+weld | r20k arranged | r21c fit; L/R)
edge off CF 450/550/650: 71/66, 78/72, 94/85 | 0/0, 0/0, 6/4 | 0/0, 17/18, 34/35 | (see $FR20 tab20 log) | closed
front.L|front.R crossing (verts): 0 | 73 | carried | 62 (327-431 mm) | 0 (shirt 0)
lapel through own base share L/R: <= 2.5 % | - | 6.9/10.7 | 1.7/5.9 | 0.3/3.1 (r19a 0/6.6)
stretch p99 jacket: - | 9.7 | 7.4 | - | 18.2 (r19a 8.4)

## Open faults (game visibility first)
1. Waist tight (Joe): the shirt stands 17 mm off at the waist under the jacket (C84); sides pinched. 2. Opening: to be ARRANGED on the layered fit. 3. Collar stands up the neck like a band.
4. Lapels narrow, gorge twist; front.R lapel through its base at the gorge. 5. Shirt poke-through. 6. Neck seam
openings 5-12 mm at HPS. 7. Pinched waist + flared skirt; boxy square shoulder; thick front-edge ridge.

## Switches (module default; candidate)
pattern_form.LAP_LAYER True (new; LAP_GAP 1.5 mm, LAP_REACH 12, LAP_DEPTH 8, LAP_STEP 1, LAP_BUTTON 25 mm, LAP_FINAL
off, LAP_FINISH 16) | pattern_jacket.STAND_RUN_OFF False (candidate on) | ROLL_GAP False (candidate on) | others as
round 18. Release: zozo start_over 0.06. Arrange: ARRANGE_PULL 10 (KAT); Garrett r20k pull 100 keep.

## Dead ends (one line each)
- Gravity substitutes on the form; release neck unheld / 6 s settle / no shirt / front balance 20 mm / friction 0.
- Notch: more press weight, fall base onto lapel, R28 without the crease run-off, longer crease fade.
- Fronts' crossing: untangle_closure after the fit (r20b moved 0); in the form: a soft lap target, a raised body offset,
  a last-round all-the-way push (tore: p99 23 %); hold_ring 40 mm (CCD fails at t = 0).

## Commands ($FRn = /mnt/data/hifipushie/dress_garrett/fit_round<n>; $FR21/run.sh runs THIS worktree's code)
$FR21: job.sh / harness21.py (fit), fitcheck.sh <tag> [K=V] (fit + crossings per phase + shirt), phases.py, probe5.py
(laps + stretch per piece), probe7.py (stretched edges by depth), lapel.py (lapel through base, mapped). $FR20: g20.py
(release / arrange job), zrun.py, tab20.py, render20.py. $FR13/m10.py concept rows.

## History (grep only)
docs/notes/cloth.md "fit round 21", "fit round 20", "fit round 19".
