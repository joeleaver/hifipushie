# STATE: dress_garrett_fit (Garrett jacket + shirt: closed form fit + ONE release sim + arrangement) -- 2026-10-20, round 24

DESIGN FACT (Joe 2026-10-20, settled; checklist garrett_jacket.json reference_facts + item side_line_plumb): the jacket
"should basically just fall straight down": no waist suppression (side seams, side panels, darts, CB), side line plumb
from the chest to the hem, hanging from the chest and shoulder blades.
STATE: round 24 step 1 flat DONE (plumb cut + gate rows), step 2 (C85 visible scope) DONE, closed fits r24a (BRIDGE
off) / r24b (BRIDGE on) RUNNING. Nothing approved. Spend $0.
- Flat ($FR24/flat24.py): suit min girth 890 (18 %); "straight" 1048 (CB + dart + the block's fitted side seam still
  pinched); PLUMB (pattern_jacket silhouette "plumb" + block fitted False + no CB contour, spec wrapper $FR24/fr24.py):
  chest 1158 (book ease kept, +14.9 % without the lap), narrowest chest->hips 1143, hips 1143. Gate rows waist_plumb
  (>= chest x 0.97, hips >= it), waist_suppression <= 3 %, front_dart absent.
- C85 visible scope: cloth_check.VISIBLE_SCOPED / visible_fit_rows / rejudge_under_visible; fit_garment re-judges the
  shirt's under_standoff_waist on its VISIBLE vertices when that is its only failing row (provisional), rewrites the
  shirt's fit record, refuses only if it still fails.
- Poke-through probe ($FR24/shoulder.py on r23c): not the cull (a poking vertex is outside the jacket, so drawn);
  geometric: shirt 3-8 mm out at the front by the neck (|x| 70-110), 1-3 mm at the shoulder seam / cap.
RENDERS: none yet this round. r23c: $FR23/check/*.
NEXT: r24a/b numbers ($FR24/sideline.py + sum23.py: widths, side line, seat cup, stretch, poke) -> pick; poke lever
(the export's own rule cloth_layers.tucked on the fit, measured before / after); renders $FR24/check; reviews.

## Method (Joe 2026-10-20)
Open jacket = the BUTTONED fit on the dress form (pattern_form.assemble, top button fastened), then ONE short release
sim (cloth_release, MCP release_garment; docs/state/cloth_release.md), then ARRANGED (MCP arrange_garment). The concept's
opening (edge off CF 71/78/94 at 450/550/650, break x 64, V width 237) is reached by arranging, never by fit levers.
Under garments fit on their own first (C85; rows about hidden cloth judged on what shows); layered pairs: the over
garment over the body + the under's allowance (outer_first LAYER_ALLOW 0.008), the under garment kept only where seen
(B: cloth_layers.hidden, front margin 120 mm = cloth_check.OPEN_FRONT_MARGIN).

## Table (concept | r23c suit + bridge + cull | r24a plumb | r24b plumb + bridge)
front-view widths chest / waist / hip / seat / hem+30: 397 / 414 (m10 401) / - / 413 / 482 | 414 / 319 / 398 / 433 / 425
side line in from plumb (max, mm): 0 | 49 at -225 below the chest | |
CB seat cup: - | 36 ; waist girth over body: - | +104 ; stretch p99: - | 15.6
shirt poke (drawn verts out > 1 mm): 0 | 280 (shoulder 45)

## Open faults (game visibility first)
1. Waist pinch: the draft (C88) -> plumb cut (this round). 2. Seat bulge + hem curling in under the seat. 3. Opening:
to be ARRANGED. 4. Collar stands up the neck. 5. Lapels narrow, gorge twist; front.R lapel through its base at the
gorge. 6. Shirt poke-through (neck front, shoulders). 7. Neck seam openings 5-12 mm at HPS. 8. Inflated ease / thick
edges; domed shoulder; wide sleeves.

## Switches (module default; candidate)
pattern_jacket silhouette suit (default) / straight / plumb (Garrett: plumb via the spec); pattern_form: BRIDGE False
(opt-in) + BRIDGE_HANG True; LAP_LAYER True; layered_fit "lie" / "outer_first" (LAYER_ALLOW) / "joint";
WAIST_OVER_BODY 0.10 (C84). cloth_check.UNDER_STANDOFF 10 mm (C85), VISIBLE_SCOPED. Release start_over 0.06.

## Dead ends (one line each)
- Gravity substitutes on the form; release neck unheld / 6 s settle / no shirt / front balance 20 mm / friction 0.
- Notch: more press weight, fall base onto lapel, R28 without the crease run-off, longer crease fade.
- Fronts' crossing: untangle_closure; soft lap target; raised body offset; last-round push; hold_ring 40 mm.
- Waist (suit cut): laying the shirt down (r22a), a body + 8 mm floor (r22b), bridging the form (r23a/c).

## Commands ($FRn = /mnt/data/hifipushie/dress_garrett/fit_round<n>; $FR24/run.sh runs THIS worktree's code)
$FR24: MODE=outer ./fitcheck.sh <tag> LAYER_ALLOW=0.008 [BRIDGE=true] (spec fr24.py; CUT=suit control); flat24.py
<variants> (flat girths + rows), pieces24.py, sideline.py <asm> (widths, side line, poke), shoulder.py <asm>,
sum23.py (seat cup), render23.py <asm> <tag> [views], beforeafter.py.
