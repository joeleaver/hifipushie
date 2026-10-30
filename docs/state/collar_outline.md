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
1. Small kink at each leaf's front corner tip (where the band end, the collar end and the fold turn meet). Two fixes
   failed (rigid roll tie radius; blending the end edge into the turn): next = model the corner as its own small
   rigid patch (like the point triangle) at the end of the fold.
2. Hang the soft fronts / yoke from the open band (not yet).
3. Library: a general `outline` module (chains, cross lines, stiffness, contact, surfaces) + MCP tool; then cuffs,
   lapels, a whole simple garment, transfer-tested on another body.

STATE: shape nailed for closed + open collar (spike). NEXT: corner patch, then fronts hang from the band.
