# STATE: dress_garrett_fit (Garrett jacket + shirt: closed form fit + ONE release sim + arrangement) -- 2026-10-20, round 24

DESIGN FACT (Joe 2026-10-20, settled; checklist garrett_jacket.json reference_facts + item side_line_plumb): the jacket
"should basically just fall straight down": no waist suppression (side seams, side panels, darts, CB), side line plumb
from the chest to the hem, hanging from the chest and shoulder blades. Reviewers asking for waist shaping: dispute.
STATE: round 24 steps 1-3 + 5 done, step 4 (release) not started. Candidate r24c (plumb cut + BRIDGE + new cull).
Nothing approved. Spend $0 (no ZOZO this round).
- Cut (C89): pattern_jacket silhouette "plumb" + block fitted False + no CB contour (spec wrapper $FR24/fr24.py). Flat
  min girth chest->hips 890 (suit) -> 1143; chest ease kept (+14.9 %). Rows waist_plumb, waist_suppression <= 3 %,
  front_dart absent.
- Fit: BRIDGE now helps (with girth). r24b/c front view waist 398 (concept 401), seat 413 (413), chest 409 (397), hem
  +30 429 (482); side line within ~9 mm of plumb but one row 14 / 22; CB seat cup 36 -> 26; stretch p99 16.0.
- C85 visible scope (C90): under rows about hidden cloth re-judged on what shows (fit_garment, provisional).
- Poke (C91): the cull, not the fit: 120 mm margin round the whole front edge kept the shirt up to the shoulders ->
  margin below the break only (LAPEL_MARGIN 85 above) + pierce 15 mm. Drawn pokes 125 -> 72; patches mostly gone.
RENDERS $FR24/check: wholefront_r24c.png, upper_front_r24c.png (ref | clay | diag), side_before_r23c_after_r24c.png,
back_before_r23c_after_r24c.png (clay before | after | diag before | after); r24b = before the recull.
REVIEWS: $FR24/rev_wf FAIL (boxy = Joe's call; too much ease, fronts stand off; see-through specks; puffy thick hang;
shoulders wide / square); $FR24/rev_side_ab: NEW (r24c).
NEXT: (1) coordinator / Joe: look at the straight cut (side / back sheets). (2) Ease: the fronts stand off (waist +184
over the body; the draft's chest ease 15 % + the lap): measure ease vs the concept per height before any lever.
(3) Pocket flaps sunk under the fronts (new in r24); chest specks + the crossing below the button. (4) Release on the
layered fit (t = 0 CCD fail: lap gap vs ZOZO's contact gap), arrangement (r20k setup). (5) Cull margin split untested.

## Method (Joe 2026-10-20)
Open jacket = the BUTTONED fit on the dress form (pattern_form.assemble, top button fastened), then ONE short release
sim (cloth_release, MCP release_garment; docs/state/cloth_release.md), then ARRANGED (MCP arrange_garment). The concept's
opening (edge off CF 71/78/94 at 450/550/650, break x 64, V width 237) is reached by arranging, never by fit levers.
Under garments fit on their own first (C85; hidden-cloth rows judged on what shows, C90); layered pairs: the over
garment over the body + the under's allowance (outer_first LAYER_ALLOW 0.008), the under kept only where seen (B:
cloth_layers.hidden, cloth_check.open_front_margin, pierce PIERCE_CULL).

## Table (concept | r23c suit + bridge | r24a plumb | r24c plumb + bridge + new cull)
front-view chest / waist / hip / seat / hem+30: 397 / 401-414 / - / 413 / 482 | 414/319/398/433/425 | 407/360/345/382/408
| 409/398/394/413/429 ; side line max in L/R: 0 | 49/49 | 31/55 | 14/22 ; CB seat cup: - | 36 | 74 | 26
waist girth over body: +104 | +188 | +184 ; stretch p99: 15.6 | 14.8 | 16.0 ; drawn shirt pokes: 157 | - | 72

## Open faults (game visibility first)
1. Too much ease / fronts stand off; puffy thick hang. 2. Opening: to be ARRANGED. 3. Collar stands up the neck.
4. Lapels narrow, gorge twist. 5. Fronts cross below the button (lilac specks). 6. Pocket flaps sunk (r24). 7. Shoulders
wide / square, wide sleeves. 8. Neck seam openings 5-12 mm at HPS. 9. Hem +30 width 429 vs 482.

## Switches (module default; candidate)
pattern_jacket silhouette suit (default) / straight / plumb (Garrett: plumb via the spec); pattern_form BRIDGE False
(candidate True) + BRIDGE_HANG True; LAP_LAYER True; layered_fit outer_first (LAYER_ALLOW); cloth_check UNDER_STANDOFF
10 mm, VISIBLE_SCOPED, OPEN_FRONT_MARGIN 120, LAPEL_MARGIN 85; cloth_layers.hidden pierce default 2 mm (PIERCE_CULL 15).

## Dead ends (one line each)
- Gravity substitutes on the form; release neck unheld / 6 s settle / no shirt / front balance 20 mm / friction 0.
- Fronts' crossing: untangle_closure; soft lap target; raised body offset; last-round push; hold_ring 40 mm.
- Waist (suit cut): shirt laid down, body + 8 mm floor, bridging (r22-r23). Poke: tucked on the fit (r24, moves 58 mm).

## Commands ($FRn = /mnt/data/hifipushie/dress_garrett/fit_round<n>; $FR24/run.sh runs THIS worktree's code)
$FR24: MODE=outer ./fitcheck.sh <tag> LAYER_ALLOW=0.008 BRIDGE=true (spec fr24.py, CUT=suit control); flat24.py
<variants>; sideline.py / rings.py / shoulder.py <asm>; sum23.py; cullrender.sh <src> <dst> [views]; beforeafter.py.
