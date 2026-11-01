# STATE: collar_outline -> garments built from the pattern's outline (2026-10-29)

Joe 2026-10-29: "That's pretty damn good ... This is how we should build clothes, right here."
GOAL: stiff / folded pieces (collar, band, cuffs, plackets, lapels), then whole garments, built as CHAINS of the
pattern's own lengths with only bends chosen; surfaces filled between; soft parts hang from the stiff ones.

## Current best
- Open collar Q5S, closed collar O15S: renders /mnt/data/hifipushie/folds_ab/D/ (Q5S_collar_plain.png, Q5S_zooms.png).
- Code + recipe: spikes/collar_outline/README.md (outline.py, band_open.py, surfaces.py, look*.py). Ledger C259, C260.
- Rules: lengths hard, bends free; stiff parts keep their own shape (pressed curve round the back, straight past the side
  neck); contact = can't sink in + light rest; cross lines may shorten only where the cloth curves; point triangles
  rigid; outside faces out, band upright; open = stiff band's own shape unbuttoned, collar solved on the held band;
  surfaces: fold turn = half circle (2.4 mm) round the band top, fall filled, band kept under the fall.
- Judge: the piece alone, large, 4 sides, curves drawn; reference photos (folds_ab/refs) for the IDEA of the style.

## Open (ranked)
1. DONE (Joe chose B): corner patch - the last 10 mm of each leaf copies the clean profile 10 mm inside, rigidly along
   the seam, blended out over 8 mm / 16 mm; a slight angle change remains where it blends out.
2. Hang the soft fronts / yoke from the open band (not yet).
3. Library: a general `outline` module (chains, cross lines, stiffness, contact, surfaces) + MCP tool; then cuffs,
   lapels, a whole simple garment, transfer-tested on another body.

## Upper shirt as a chain network (upper.py, best Q12U; band U4 -> outline Q12 -> surfaces Q12 -> `upper.py Q12 '{"below":0.02,"iters_d":600,"passes":40}'`)
Every edge of back, yoke, fronts is a chain; seams merged; button 1 a pivot tied to the chains by lines across the placket;
held: band neckline, armholes, cloth from 2 cm below the button. The band's whole sewn front is limited by its cut distance
to button 1. Each placket is a rigid strip (edge .. marked fold line, the mesh is one layer) that folds out of plane along
a solved crease through button 1 (L 51 deg / 110 deg fold, R -39 / 83); left lies over right. upper.py Q12
'{"below":0.02,"iters_d":300,"passes":40,"btn_r":0,"rigid_to":0.0}': the strip starts folded, only its sewn edge + the button
stay held; the fold acts on the real shape; final stages let all unheld cloth move, lengths + body floor to the end.
Free chain links <= 1.75 %; cloth inside the body 0. OPEN: 42 links > 2 % beyond the fit, worst 6.5 % (yoke by the neck +
armhole); lap gap touches 0 at one point. No gravity hang yet. NICO-TOP unavailable (Joe 2026-11-01): sims local.

## Hang (local ZOZO, 284 s on the 890M; result H1)
hang_prep.py Q12 h1 -> hang_run.py h1 -> hang_finish.py h1 H1 Q12, RUN WITH THE PATH-A WORKTREE'S CODE (agent-a31fb4eb7a07d59fa:
zozo_hang is not on threads-hard). Torso only; band, collar, plackets above the hold line, sewn rows, armholes held;
body under the band cut from the collider (35 mm + one 12 mm patch). Free cloth moved p50 6.5, p95 16 mm; held 0.05 mm.
OPEN: 27 free vertices inside the full body (deepest 2.7 mm; skin specks under the collar at the back + side); seam gap
up to 3.4 mm; link p99 5.8 %, max 65 % (was 79.5 % before the hang); wrinkly yoke round the neck; sleeves are the old
fit's and were not hung (gap at the back armhole).

## Whole shirt hang H2 (622 s local): hang_prep.py Q12 h2 144 sleeves -> hang_run.py h2 -> hang_finish.py h2 H2 Q12; look.py / lookw.py H2
Renders now use joined.py: sewn vertices shared, every piece facing out (the pronounced seams were mostly per-piece shading).
Cuffs held; body under band + cuffs and patches at 111 contacts cut from the collider. OPEN: sleeves are the old crushed fit
hung: link p99 34 %, max 76 %; sleeves + armpit in the body up to 21 mm; skin at the back armholes. Side seams sewn only every
20 mm (2 cm body mesh). A post-hang "press" tore the chest (286 %): removed, don't repeat it.

STATE: shirt from chains, hung locally; collar, neck, torso read right. NEXT: build the sleeves from chains, then library module.
