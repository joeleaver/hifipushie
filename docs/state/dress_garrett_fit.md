# STATE: dress_garrett_fit (Garrett jacket + shirt: closed form fit + ONE release sim + arrangement) -- 2026-10-20, round 25

DESIGN FACT (Joe 2026-10-20, settled; checklist garrett_jacket.json reference_facts + item side_line_plumb): the jacket
"should basically just fall straight down": no waist suppression, side line plumb chest -> hem. Reviewers asking for
waist shaping: dispute. Joe 2026-10-20 on r24c: "that looks a lot better, not sure why you keep trying to button
though": the jacket is worn OPEN; every render shown is the OPEN, ARRANGED jacket (the buttoned fit is internal only).
STATE: round 25 step 1 (open jacket) in progress: the release of the layered fit RUNS (r25e, C92); arrangement r25f
running. Candidate fit r24c (plumb cut + BRIDGE + new cull). Nothing approved. Spend $0 (local ZOZO).
- Release t = 0 CCD fixed (C92): button pair parted (part_released), fronts off the chest (BODY_CLEAR_MOST 8 mm), shirt
  vertices under jacket faces stepped back (collider_clear) + preflight collider_vertex_pairs row.
- r25e (release, no pins): fronts barely open (edge off CF 7/12/25 at 450/550/650 vs concept 71/78/94): arrange.
NEXT: (1) r25f arrangement (r20k setup: kept light pins pull 100, edge break..cfHem to the concept rows) -> table +
renders of the OPEN jacket. (2) Ease measured on the open jacket (ease25.py per height; waist +184 over the body on r24c
vs book +110; fronts stand off; "thick" look). (3) Pocket flaps sunk (r24). (4) Chest specks + crossing below button.

## Method (Joe 2026-10-20)
Open jacket = the BUTTONED fit on the dress form (pattern_form.assemble, top button fastened), then ONE short release
sim (cloth_release, MCP release_garment; docs/state/cloth_release.md), then ARRANGED (MCP arrange_garment). The concept's
opening (edge off CF 71/78/94 at 450/550/650, break x 64, V width 237) is reached by arranging, never by fit levers.
Under garments fit on their own first (C85; hidden-cloth rows judged on what shows, C90); layered pairs: the over
garment over the body + the under's allowance (outer_first LAYER_ALLOW 0.008), the under kept only where seen (B:
cloth_layers.hidden, cloth_check.open_front_margin, pierce PIERCE_CULL).

## Table (concept | r23c suit + bridge | r24a plumb | r24c plumb + bridge + new cull | r25e released)
front-view chest / waist / hip / seat / hem+30: 397 / 401-414 / - / 413 / 482 | 414/319/398/433/425 | 407/360/345/382/408
| 409/398/394/413/429 ; side line max in L/R: 0 | 49/49 | 31/55 | 14/22 ; CB seat cup: - | 36 | 74 | 26
waist girth over body: +104 | +188 | +184 ; stretch p99: 15.6 | 14.8 | 16.0 | 13.4 ; drawn shirt pokes: 157 | - | 72
edge off CF 450/550/650 (L/R): concept 71/78/94 | r25e 7/3, 12/15, 25/28

## Open faults (game visibility first)
1. Opening: to be ARRANGED (r25f). 2. Too much ease / fronts stand off; puffy thick hang. 3. Collar stands up the neck.
4. Lapels narrow, gorge twist. 5. Fronts cross below the button (lilac specks). 6. Pocket flaps sunk (r24). 7. Shoulders
wide / square, wide sleeves. 8. Neck seam openings 5-10 mm at the stand after the release. 9. Hem +30 width 429 vs 482.

## Switches (module default; candidate)
pattern_jacket silhouette suit (default) / straight / plumb (Garrett: plumb via the spec); pattern_form BRIDGE False
(candidate True) + BRIDGE_HANG True; LAP_LAYER True; layered_fit outer_first (LAYER_ALLOW); cloth_check UNDER_STANDOFF
10 mm, VISIBLE_SCOPED, OPEN_FRONT_MARGIN 120, LAPEL_MARGIN 85; cloth_layers.hidden pierce default 2 mm (PIERCE_CULL 15).
cloth_release RELEASE_PART 2.2 mm (default on), BODY_CLEAR_MOST 4 mm (Garrett r25: 8 via g25 cr.BODY_CLEAR_MOST=0.008),
EDGE_CLEAR_MOST 2 mm (Garrett r25: 4).

## Dead ends (one line each)
- Gravity substitutes on the form; release neck unheld / 6 s settle / no shirt / front balance 20 mm / friction 0.
- Fronts' crossing: untangle_closure; soft lap target; raised body offset; last-round push; hold_ring 40 mm.
- Waist (suit cut): shirt laid down, body + 8 mm floor, bridging (r22-r23). Poke: tucked on the fit (r24, moves 58 mm).
- Release start: whole-lap parting without the layer-order test (47 crossings, r25b first try).

## Commands ($FRn = /mnt/data/hifipushie/dress_garrett/fit_round<n>; $FR25/run.sh runs THIS worktree's code)
$FR25: arr.sh <tag> [arrange=1 keep=1 pull=100] = g25.py (job from start=asm_r24c + placed_28e8e057e879) + zrun.py
(local ZOZO, capped) + tab25.py (asm_<tag>.pkl, arranged / weld / concept rows); t0.py / t0b.py <job> (t = 0 contacts);
ease25.py <asm> (ease per height); fitcheck.sh / job.sh / harness24.py (the closed fit, round 24's recipe).
