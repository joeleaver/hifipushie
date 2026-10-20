# STATE: dress_garrett_fit (Garrett jacket + shirt: closed form fit + ONE release sim + arrangement) -- 2026-10-20, round 22

STATE: round 22 step 1 (the shirt under the jacket) measured, NOT solved; steps 2-3 not started (budget). Closed fit
r21c stays the candidate. Nothing approved. Spend $0.
- FIT ORDER (C85, Joe): fit_garment / dress now refuse an outer garment until its under garment's OWN fit record
  PASSes (cloth_check.under_fit_status; rows fit_strain_p99, under_standoff_waist <= 10 mm). Garrett's shirt alone
  stands ~15 mm off at the waist: it FAILS, so the jacket is refused (force=True to look).
- The jacket's waist girth follows its FLOOR, not its pattern (C86): +119 over the standing shirt (r21c), +87 over a
  laid-down shirt (r22a, layered_fit "lie"), +97 over body + 8 mm (r22b, outer_first LAYER_ALLOW 0.008); draft +110.
  Front-view waist 318-320 on EVERY floor (concept 401): the pinch is the jacket's own shape (under-bust 371 -> waist 320
  -> hip 397 wide), not the shirt. 401 at a ~900 mm closed waist is near impossible round a 201 mm deep body.
- A vs B (coordinator): A = press the covered shirt soft (lie_under: shirt |strain| p99 58 %, jacket +87); B = cull
  early (jacket over body + the shirt's stack allowance, shirt kept only where visible: jacket +97, no compressed
  shirt). PICK B; not built yet.
RENDERS: $FR22/check/*_r22a.png (closed fit; reviews wholefront / upper_front / three all FAIL, notes).
NEXT: (1) the form's seat attraction on an OVER garment (why its girth follows the floor: r22a/r22b let_go doesn't give
the length back) -> the jacket at its draft +110 on body + allowance; (2) B: the shirt's visible-region cull (collar, V,
cuffs + a margin covering the ARRANGED open front, or the cull after arrangement), the release collider = body +
allowance, the shirt's fit gate rows judged on the allowance under the cull; (3) ask Joe (via coordinator): the
concept's waist 401 front view vs the book's suppression (a straighter cut?) -- a design call; (4) old steps 2-4:
front.R lapel dip at the gorge (probe8: LAP_LAYER does NOT act above 250 mm below HPS, so the R-only dip and the
front.R neck stretch 8.4 -> 18.2 % come from elsewhere: lap_order's start lift or the seat; trace with $FR22/probe9.py),
the t = 0 CCD fail (lap gap 1.5 mm vs ZOZO's contact gap), release + arrangement (r20k setup), table + reviews.

## Method (Joe 2026-10-20)
Open jacket = the BUTTONED fit on the dress form (pattern_form.assemble, top button fastened), then ONE short release
sim (cloth_release, MCP release_garment; docs/state/cloth_release.md), then ARRANGED (MCP arrange_garment). The concept's
opening (edge off CF 71/78/94 at 450/550/650, break x 64, V width 237) is reached by arranging, never by fit levers.
Under garments fit on their own first (C85); layered pairs: the over garment over the body + the under's allowance, the
under garment kept only where seen (B, coordinator 2026-10-20).

## Candidates (nothing approved)
- Fit r21c ($FR21/fitcheck.sh r21c) -> $FR21/asm_r21c.pkl. r22a (lie) / r22b (outer_first 8 mm): $FR22/asm_r22{a,b}.pkl,
  comparisons only. r20k arranged ($FR20/asm_r20k.pkl).

## Table (concept | r20k arranged | r21c fit | r22a lie | r22b outer 8 mm)
jacket waist over body: draft +110 | +143 | +119 | +87 | +97
jacket waist over shirt (>= 25 mm): - | +33 | +11 | +30 | +2 (shirt culled under B)
front-view waist width: 401 | 317 | 320 | 318 | 319
shirt off body at waist p50 (<= 10): - | - | 15.1 | 8.0 | 12.0
front.L|front.R crossing: 0 | 62 | 0 | 0 | 0 ; shirt fronts 0 | - | 0 | 0 (lap kept) | 0
stretch p99 jacket: - | - | 18.2 | 15.3 | 14.9

## Open faults (game visibility first)
1. Waist pinch (Joe "tight around his middle"): the jacket's own shape + form attraction (C86). 2. Opening: to be ARRANGED.
3. Collar stands up the neck. 4. Lapels narrow, gorge twist; front.R lapel through its base at the gorge. 5. Shirt
poke-through. 6. Neck seam openings 5-12 mm at HPS. 7. Flared skirt; boxy square shoulder; thick front-edge ridge.

## Switches (module default; candidate)
pattern_form: LAP_LAYER True; layered_fit modes "lie" (new, UNDER_LIE_CAP 8 mm, UNDER_LIE_GATHER 0.10, opt-in) /
"outer_first" (LAYER_ALLOW) / "joint"; WAIST_OVER_BODY 0.10, WAIST_OVER_UNDER 2 pi EASE (waist_layers, C84).
cloth_check.UNDER_STANDOFF 10 mm (C85). pattern_jacket STAND_RUN_OFF / ROLL_GAP candidate on. Release start_over 0.06.

## Dead ends (one line each)
- Gravity substitutes on the form; release neck unheld / 6 s settle / no shirt / front balance 20 mm / friction 0.
- Notch: more press weight, fall base onto lapel, R28 without the crease run-off, longer crease fade.
- Fronts' crossing: untangle_closure; soft lap target; raised body offset; last-round push; hold_ring 40 mm.
- Waist: laying the shirt down (r22a) or a body + 8 mm floor (r22b): the jacket follows the floor in, width unchanged.

## Commands ($FRn = /mnt/data/hifipushie/dress_garrett/fit_round<n>; $FR22/run.sh runs THIS worktree's code)
$FR22: MODE=lie|outer ./fitcheck.sh <tag> [K=V]; gate84.py (C84 row), widths.py (chest / waist / hip widths), probe10.py
(waist strain + stand-off), presssweep.py (lie_under on a saved standing shirt), probe8.py (where LAP_LAYER acts),
probe9.py (front neck stretch per phase), render21.py <asm> <tag> [views]. $FR20: g20.py, zrun.py, tab20.py.

## History (grep only)
docs/notes/cloth.md "fit round 22", "fit round 21", "fit round 20".
