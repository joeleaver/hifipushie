# STATE: dress_garrett_fit (Garrett jacket + shirt: closed form fit + ONE release sim + arrangement) -- 2026-10-20, round 26

NOTE (2026-10-21): the shirt under the jacket changes with the shirt spike's landed defaults (Simon's band sewn edge to
edge, KB no_tie open-neck rolls removed, collar + stand 2 mm on the form, BUILD_VERSION 17): refit the shirt before the
jacket over it. docs/state/collar_spike.md, ledger C137-C140.

DESIGN FACTS (Joe, settled): the jacket is worn OPEN, unbuttoned ("no, it's not buttoned"); it "should basically just
fall straight down" (no waist suppression, side line plumb). Reviewers keep reading the reference as fastened: put
"the reference jacket is worn open, unbuttoned" in every review's context; a "fastened" reading is a known misread,
not a finding. Everything rendered is the OPEN, ARRANGED jacket; the closed fit is an internal stage, never A/B'd.
STATE: round 26 done: r26k = closed fit r26i (tube-sized plumb cut C94 + pocket flaps as patches C95) -> release ->
arrangement with the side seams held (C96) -> recull with the shirt hidden below the belt line (BELT=50, stand-in until
trousers). Blind wholefront review FAIL (11 MAJOR incl. the known "fastened" misread); A/B r25g vs r26k: NEW.
$0 spent (local ZOZO). Nothing approved.
NEXT: (1) pocket flaps read "puffy rolls", ~50 px low (they now lie on the front: thickness / roll of the made flap
+ its height on the pattern). (2) Hem corners crumpled / ragged at the lower fronts (arrangement pins at cfHem).
(3) Length: our cfHem 758 / side hem 759 below HPS vs round 13's concept 748 (+10), but the scale-matched sheet shows
our hem ~45-55 mm below the reference's: re-read the 748 before shortening. (4) Queued: collar standing up the neck,
wide square shoulders / baggy sleeves, narrow lapels / gorge, fronts crossing below the button, draft every visible
part (buttons, chest welt). (5) Shirt: tuck rule for real (design key) instead of the render-time belt cull.

## Method (Joe 2026-10-20)
Open jacket = the BUTTONED fit on the dress form (pattern_form.assemble, top button fastened), then ONE short release
sim (cloth_release; docs/state/cloth_release.md), then ARRANGED (arrange_job, kept soft pins pull 100 on break..cfHem
to the concept rows + round 26: the fronts' side seams sideF.a..sideF.b held as fitted, g25.py side=1). Layered pairs:
outer_first LAYER_ALLOW 0.008, the under kept only where seen (cull).

## Table (concept | r24c/r25f old | r26c / r26g closed | r26k open arranged); sideline.py front-view widths
chest / waist / hip / seat / hem+30: 397 / 401 / - / 413 / 482 | r25f open 384/426/445/492/438 | r26g closed
413/398/406/409/410 | r26j/k open 411/382/400/411/430. Side line in from plumb (open): r26k <= 18 (mostly <= 12).
Girth (ease25, closed): waist 1111 (r24c) -> 1060 (r26g; tube 995 + 60 = 1055); seat 1113 -> 1084.
Edge off CF 450/550/650 (concept 71/78/94): r26j 65/67, 78/64, 95/87. Springback <= 2.5 mm.
Pocket flaps off their front (p50, sunk of 25): r25f -1.2/-3.8 (20+) | r26i closed +1.5/+1.5 (0) | r26j +2.8/+3.7 (<= 1).
Shirt drawn below the waist: r25g 3242 verts -> r26j 2403 -> r26k belt cull (3987 more triangles hidden).

## Levers this round (kept / dead)
- C94 plumb cut to the tube: shares at the side seams (r26a) pinched the front view (waist 382 vs chest 416): DEAD;
  CB-led shares (0.70 / 0.30 / 0) stay plumb (r26g): KEPT (module default).
- Lower fronts swinging out: (a) edge hung plumb in depth from the break (hang=plumb, r26e): seat 464, WORSE, dead;
  (b) side seams held as fitted (side=1, r26f/h/j): seat 404-411: KEPT (arrangement script, not a module default yet).
- C95 patches on their base: KEPT (pattern_form.PATCH_ON_BASE default True).

## Switches (module default; candidate)
pattern_jacket plumb + PLUMB_ALLOW 60 mm, PLUMB_RAMP 0.10, PLUMB_SHARE cb .70 / side_back .30; tailor plumbGirth;
pattern_form PATCH_ON_BASE True, BRIDGE (candidate True), LAP_LAYER True; layered_fit outer_first; cloth_layers
PIERCE_CULL 15; cloth_release RELEASE_PART 2.2 mm, BODY_CLEAR_MOST 8 / EDGE_CLEAR_MOST 4 (Garrett).

## Dead ends (one line each)
- Gravity substitutes on the form; release neck unheld / 6 s settle / no shirt / front balance 20 mm / friction 0.
- Fronts' crossing: untangle_closure; soft lap target; raised body offset; last-round push; hold_ring 40 mm.
- Waist (suit cut): shirt laid down, body + 8 mm floor, bridging (r22-r23). Poke: tucked on the fit (r24).
- Release start: whole-lap parting without the layer-order test (47 crossings).
- Plumb cut taken at the side seams (r26a); open edge hung plumb in depth (r26e).

## Commands ($FR26 = /mnt/data/hifipushie/dress_garrett/fit_round26; run.sh runs THIS worktree's code)
Closed fit: MODE=outer ./fitcheck.sh <tag> LAYER_ALLOW=0.008 BRIDGE=true (-> asm_<tag>.pkl; new placed_<key> in
fit_round15 when the draft changes: ls -t). Release + arrange: BASE=<asm> ./arr.sh <tag> arrange=1 keep=1 pull=100
side=1 start=<asm> placed=<placed pkl>. Renders: BELT=50 ./cullrender.sh <src> <dst> wholefront,upper_front,
upper_three,side,back. Measures: sideline.py, ease25.py, flaps25.py, len26.py. Reviews: rev26.sh wf | ab.
