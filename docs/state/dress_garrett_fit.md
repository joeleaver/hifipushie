# STATE: dress_garrett_fit (Garrett jacket + shirt: closed form fit + ONE release sim + arrangement) -- 2026-10-20, round 25

DESIGN FACT (Joe 2026-10-20, settled; checklist garrett_jacket.json reference_facts + item side_line_plumb): the jacket
"should basically just fall straight down": no waist suppression, side line plumb chest -> hem. Reviewers asking for
waist shaping: dispute. Joe 2026-10-20 on r24c: "not sure why you keep trying to button though": show the OPEN,
ARRANGED jacket (the buttoned fit is an internal stage).
OPEN QUESTION FOR JOE (round 25): both blind reviewers, unprompted, read the reference as FASTENED at the waist button
(V ends there, cutaway below), and my own look agrees; the front A/B chose closed r24c over open r25g for that reason.
Worn fully open (concept rows 71/78/94) or one button fastened at the waist? Not decided here.
STATE: round 25 step 1 done: the release of the layered fit RUNS (C92) and is ARRANGED open (r25f, $0 local ZOZO):
edge off CF 67/66, 78/71, 95/87 at 450/550/650 (concept 71/78/94), springback <= 1 mm, still 1.8 mm. Renders r25g.
Ease and flaps MEASURED (causes found), not changed. Nothing approved. Spend $0.
NEXT: (1) Joe: open vs fastened at the waist (if fastened: the release keeps the waist button = closure_stitches on that
pair; arrange only below it). (2) Ease: pattern_jacket plumb keeps the chest's full-ease girth to the hem (+116 over
the plumb minimum 995 below the chest, ~+55 surplus after the shirt allowance; excess at the sides / back: stand-off
side 71, back 62 at the waist): size the plumb girth to max(plumb minimum + allowances, chest need); waist_plumb gate
row gets a ceiling. (3) Pocket flaps: placed off the BODY at the old offset while the fronts moved out (BRIDGE + plumb):
draw them onto their base front (+ THICK). (4) Too long (hem at the crotch; reviewer), collar up the neck, lower fronts
swing out (seat width 492 vs 413 when arranged). (5) Chest specks / crossing below the button: not re-measured.

## Method (Joe 2026-10-20)
Open jacket = the BUTTONED fit on the dress form (pattern_form.assemble, top button fastened), then ONE short release
sim (cloth_release; docs/state/cloth_release.md), then ARRANGED (arrange_job, kept soft pins pull 100 on break..cfHem
to the concept rows = the r20k setup). The opening is reached by arranging, never by fit levers. Layered pairs: the over
garment over the body + the under's allowance (outer_first LAYER_ALLOW 0.008), the under kept only where seen (cull).

## Table (concept | r24c closed | r25e released | r25f arranged)
front-view chest / waist / hip / seat / hem+30: 397 / 401 / - / 413 / 482 | 409/398/394/413/429 | 410/404/420/428/438
| 412/427/464/492/511 ; edge off CF 450/550/650: 71/78/94 | closed | 7, 12, 25 | 67, 78, 95 (L)
girth (ease25, exact): body waist 789, plumb minimum 995; r24c chest 1168, below chest ~1112 ; stretch p99 16.0 | 13.4 | 13.5

## Open faults (game visibility first)
1. Open vs fastened (Joe). 2. Too much ease at sides / back; boxy; "thick" look (not measured yet: cloth thickness /
2.2 mm lapel shell). 3. Pocket flaps sunk (cause found). 4. Too long. 5. Collar stands up the neck. 6. Lapels narrow,
gorge twist. 7. Shoulders wide / square, wide sleeves. 8. Neck seams open 5-10 mm at the stand after the release.

## Switches (module default; candidate)
pattern_jacket silhouette plumb (Garrett via the spec); pattern_form BRIDGE (candidate True), LAP_LAYER True;
layered_fit outer_first; cloth_check LAPEL_MARGIN 85; cloth_layers PIERCE_CULL 15. cloth_release RELEASE_PART 2.2 mm
(on), BODY_CLEAR_MOST 4 mm (Garrett: 8), EDGE_CLEAR_MOST 2 mm (Garrett: 4), collider_clear (on); cloth_job.preflight
collider_vertex_pairs row (new, in ok).

## Dead ends (one line each)
- Gravity substitutes on the form; release neck unheld / 6 s settle / no shirt / front balance 20 mm / friction 0.
- Fronts' crossing: untangle_closure; soft lap target; raised body offset; last-round push; hold_ring 40 mm.
- Waist (suit cut): shirt laid down, body + 8 mm floor, bridging (r22-r23). Poke: tucked on the fit (r24).
- Release start: whole-lap parting without the layer-order test (47 crossings).

## Commands ($FRn = /mnt/data/hifipushie/dress_garrett/fit_round<n>; $FR25/run.sh runs THIS worktree's code)
$FR25: arr.sh <tag> [arrange=1 keep=1 pull=100] (g25.py job from asm_r24c + placed_28e8e057e879, zrun.py local ZOZO,
tab25.py -> asm_<tag>.pkl); cullrender.sh <src> <dst> [views]; beforeafter.py; t0.py / t0b.py <job> (t = 0 contacts);
ease25.py <asm> (ease per height + plumb minimum); flaps25.py <asm>; fitcheck.sh / job.sh / harness24.py (closed fit).
