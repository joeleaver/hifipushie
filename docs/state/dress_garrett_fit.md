# STATE: dress_garrett_fit (Garrett jacket over the approved shirt gc1: closed form fit + ONE release sim + arrangement) -- 2026-10-22, round 28

DESIGN FACTS (Joe, settled): the jacket is worn OPEN, unbuttoned; it falls straight down (no waist suppression, side
line plumb). Put "the reference jacket is worn open, unbuttoned" in every review's context ("fastened" = known misread).
Renders show the OPEN, ARRANGED jacket only; the closed fit is internal. Show-through of a COVERED under-layer is not a
fault (C153), but SEEN under-layer cloth renders exactly as approved (C158). The shirt is gc1 (workspace gc_garrett,
/mnt/data/hifipushie/garrett_collar/gc1_styled.pkl), used AS IS; its bumpy placket is gc1's own (not a jacket fault).
STATE: round 28 in progress. Step 1 DONE: the cull (cloth_layers.hidden) is by VISIBILITY in every judged view (C158);
r27sc's "thrashed shirt" was the cull: now the shirt collar renders as CULL=0. Step 2 (Joe's belly crumple) measured,
cause found (the release, not the closed fit), NOT solved; r28h (plumb hang) kept: crumple p95 14.5 -> 12.4 mm.
Step 3 (collar at the neck, lapel / gorge) in progress on r28hc. Nothing approved. $0 spent.
NEXT: (1) collar at the neck on r28hc with the fixed cull (funnel? the shirt collar pokes through the jacket collar:
467 verts > 1 mm outside); (2) crumple: a pattern lever (less lap / width below the break for an always-open front) or
a design call; (3) cloth._worn_levels stray start vertex on graded meshes (fix27.py); garment_pull layer floor (C157).

## Method
Closed fit: r27a0 (round 27: pattern_form.assemble over gc1, top button fastened, FORM_REFINE_LAPEL, no extra refine).
Release + arrange (round 28 base r28h): g25.py arrange=1 keep=1 pull=100 side=1 hang=plumb (local ZOZO). Cull:
recull28.py (cloth_layers.hidden visibility rule) + BELT=50 on torso pieces only (round 27's belt hid the cuffs).

## The cull (C158; tests/test_cloth_layers.py)
Hidden only where the jacket or body is > 1.5 mm in front in ALL 72 judged directions (front, 3/4 at 37 / 45, sides,
back, each +-10 deg az / el), seen set grown 2 rings, made pieces whole if any triangle shows, holes / islands < 200
merged (seen never removed). rule="margin" = the old distance rule, only for a closed fit worn open. r27sc: 21968 ->
14244 hidden of 40342; stand / collar / yoke / cuffs 0. Sheet: fit_round28/check/collar_cull_before_after.png.

## Belly crumple (crumple28.py band flap top -> break; p95 mm L / R, tilt p95)
closed r27a0 3.5 / 3.9 (10 / 5) | r27s 14.5 / 12.8 (40 / 34) | r28e ends 11.7 / 10.7 (41) edges fell in | r28h plumb
12.4 / 11.4 (24 / 33) KEPT | r28p pull 10 10.2 / 10.6 edges in | r28t sides held above waist 12.0 / 10.7 | r28f +
facing to hem 12.4 / 11.5. One ridge ~12 mm parallel to the edge, 20-60 mm in, 50-57 mm off the shirt (not the shirt).
Cause: the opened edge travels ~95-120 mm out while the side seam is held: chord edge -> side 210 -> 140 mm.

## Table (concept | r27s(c) | r28h(c))
edge off CF 450/550/650 L|R: 71,78,94 | 67,77,93 / 65,71,86 | 67,77,91 / 63,69,83
side line in max L/R: - | 32/21 | 20/21.  flaps p50 off front (sunk/25): | 5.1/4.7 (0/1) | 3.2/4.4 (1/1)
widths chest/waist/hip/seat/hem+30: 397/401-414/-/-/482 | 407/391/396/396/399 | 406/393/396/394/403

## Commands ($FR28 = /mnt/data/hifipushie/dress_garrett/fit_round28; run.sh runs THIS worktree's code)
Release: BASE=$FR27/asm_r27a0.pkl ./arr.sh <tag> arrange=1 keep=1 pull=100 side=1 hang=plumb start=$FR27/asm_r27a0.pkl
placed=/mnt/data/hifipushie/dress_garrett/fit_round15/placed_5beb81fe9475.pkl [edge=ends|xz] [side=top] [facing=m].
Cull: BELT=50 ./run.sh recull28.py <asm> <out>. Render: ROUT=$FR28 RUNNER=bin/capped ./run.sh render23.py <asm> <tag>
<views>. Reads: crumple28.py, where28.py, excess28.py, ontop28.py, sideline.py, flaps25.py, belly.py (crop).

## Dead ends (one line each)
- Gravity substitutes; release neck unheld / 6 s settle / friction 0; fronts' crossing fixes (see cloth.md r20-r25).
- Plumb cut at the side seams (r26a); open edge hung plumb WITHOUT side holds (r26e).
- Roll rows graded to 2.2 mm (r27a, C156). No-sim styling without a layer floor (C157).
- Crumple: edge pinned at ends only (r28e), soft pull 10 (r28p), sides held above waist (r28t), facing band (r28f).
