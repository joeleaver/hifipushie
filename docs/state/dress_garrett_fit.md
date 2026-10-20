# STATE: dress_garrett_fit (Garrett jacket + shirt: closed form fit + ONE release sim + arrangement) -- 2026-10-20, round 23

STATE: round 23 steps 1-3 done, 4 (release) not started. The waist pinch is the DRAFT, not the form (C88). Form bridging
(C87) built, OPT-IN: it halved the seat cup by the numbers but the blind side A/B chose the old fit. Nothing approved.
Spend $0. Closed fit candidates: r22b (BRIDGE off, as default) / r23c (BRIDGE on + the shirt culled, B).
- MEASURED ($FR23/columns.py, sum23.py, girths.py): at the waist the jacket sits 9-20 mm off the body at the side seam,
  i.e. 29-46 mm inside the column's straight edge (it follows the hollow); CB already bridges (+41-51). Its waist girth
  on the form is +94-104 over the body (draft +110) where bridging the waist would need ~+300: the form can only
  redistribute. Front-view waist 305-320 on every variant (concept 401).
- BRIDGE (pattern_form.BRIDGE False, _Bridged, bridge_fraction, BRIDGE_HANG): the seat attraction's target = the body
  with its hollows filled along z (per column the concave hull, plumb below the seat), by the KB fabric's bending
  length (12 mm -> 0, 18 -> 1; suiting 0.67, shirting 0). KAT test_bridge_hourglass_tube (mechanism only).
- B cull: harness23 computes cloth_layers.hidden(..., edge_margin={"front": 0.12}) -> asm["under_hidden"]; render23
  draws the shirt culled (16456 / 29309 triangles hidden).
- Reviews: wholefront clay FAIL (6 MAJOR: hourglass "women's fitted jacket", inflated ease / thick edges, domed
  shoulders, wide sleeves, funnel collar, shirt poke-through at the shoulders). Side A/B r22a vs r23c: OLD.
RENDERS: $FR23/check/{wholefront,side,back,upper_front}_r23c.png, side_before_r22a_after_r23c.png (the key image).
NEXT: (1) JOE (via coordinator), design call with numbers: a straighter cut. The concept's waist 401 front view needs
the side seams' waist suppression taken out (jacket waist girth now +99-104 over body, draft +110 ~14 %; a ~401 front
view at ~200 mm body depth needs roughly +250-300); reviewer: "near-straight side line, only slight waist
suppression". (2) C85 with B: judge the shirt's fit rows (under_standoff_waist) on its VISIBLE region only (cull),
else the jacket stays refused. (3) The hem curl under the seat (both r22a and r23c: "padded shorts"): locate first
(which piece / phase; TRACE) before a lever. (4) old: front.R lapel dip at the gorge (probe9), the t = 0 CCD fail (lap
gap vs ZOZO's contact gap), release + arrangement (r20k setup), table + reviews.

## Method (Joe 2026-10-20)
Open jacket = the BUTTONED fit on the dress form (pattern_form.assemble, top button fastened), then ONE short release
sim (cloth_release, MCP release_garment; docs/state/cloth_release.md), then ARRANGED (MCP arrange_garment). The concept's
opening (edge off CF 71/78/94 at 450/550/650, break x 64, V width 237) is reached by arranging, never by fit levers.
Under garments fit on their own first (C85); layered pairs: the over garment over the body + the under's allowance
(outer_first LAYER_ALLOW 0.008), the under garment kept only where seen (B: cloth_layers.hidden, front margin 120 mm).

## Table (concept | r21c fit | r22a lie | r22b outer 8 mm | r23a bridge | r23c bridge + hang + cull)
front-view waist width: 401 | 320 | 318 | 319 | 305 | 319 ; hip - | - | 388 | 388 | 396 | 398 ; seat 413 | 413 | 432 | 433
jacket waist over body: draft +110 | +119 | +94 | +99 | +99 | +104
CB seat cup (seat r - hem+30 r, 0 = plumb): - | - | 82 | 80 | 39 | 36 ; back 45 deg: 13 | 10 | 4 | 4
stretch p99 jacket: - | 18.2 | 15.3 | 14.9 | 15.5 | 15.6

## Open faults (game visibility first)
1. Waist pinch = draft suppression (C88): Joe's call. 2. Seat bulge + hem curling in under the seat. 3. Opening: to be
ARRANGED. 4. Collar stands up the neck. 5. Lapels narrow, gorge twist; front.R lapel through its base at the gorge.
6. Shirt poke-through (shoulders). 7. Neck seam openings 5-12 mm at HPS. 8. Inflated ease / thick edges; domed shoulder.

## Switches (module default; candidate)
pattern_form: BRIDGE False (opt-in) + BRIDGE_HANG True (acts only with BRIDGE); LAP_LAYER True; layered_fit "lie" /
"outer_first" (LAYER_ALLOW) / "joint"; WAIST_OVER_BODY 0.10 (C84). cloth_check.UNDER_STANDOFF 10 mm (C85).
pattern_jacket STAND_RUN_OFF / ROLL_GAP candidate on. Release start_over 0.06.

## Dead ends (one line each)
- Gravity substitutes on the form; release neck unheld / 6 s settle / no shirt / front balance 20 mm / friction 0.
- Notch: more press weight, fall base onto lapel, R28 without the crease run-off, longer crease fade.
- Fronts' crossing: untangle_closure; soft lap target; raised body offset; last-round push; hold_ring 40 mm.
- Waist: laying the shirt down (r22a), a body + 8 mm floor (r22b), bridging the form (r23a/c): width unchanged.

## Commands ($FRn = /mnt/data/hifipushie/dress_garrett/fit_round<n>; $FR23/run.sh runs THIS worktree's code)
$FR23: MODE=outer ./fitcheck.sh <tag> LAYER_ALLOW=0.008 [BRIDGE=true ...]; sum23.py (round table), columns.py (gaps on
vertical lines vs the straight edge), girths.py (girth vs the bridged envelope), kat.py <bridge..> (KAT cases),
render23.py <asm> <tag> [views] (CULL=0: uncut shirt), beforeafter.py. $FR22: gate84.py, widths.py, probe9.py.
