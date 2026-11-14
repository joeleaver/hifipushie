# Feature map / sculpt from pictures: STATE 2026-11-14 (CLOSED by Joe)

Branch feature-map (worktree .claude/worktrees/feature-map), from main c3288704. For Braynard Racing (Scraps the
goat, from a three-view turnaround and a painting). Not pushed. Joe closed it: "I don't think this is going to work",
and of fitting the block-in: "Doing it parts means we got... parts, not a solid, flowing, organic looking shape".

## What holds (blind-proven or measured; worth landing as tools for SEEING and PLACING)
- Feature map: `read_reference` -> `mark_features` (mass / form / paint, marked on the pictures) -> `feature_report`
  (each feature's footprint against its mark). Fresh Opus-medium agents with the page only put every mass of Scraps in
  the right place and size in 7-8 rounds (16 of 19 right, outlines 89 / 92 / 87 %), no coordinate typed.
- `build_masses` (ball, drum, flap, trunk, tube along the mark's own middle line), `build_forms` (raise, sink, rim, band).
- `surfaceread.py`: MoGe-2 normals of ANY picture on the CPU (own venv, 16 s a picture, cached); `height()` adds the
  slopes up inside a region (pins, hidden stretches, one gain). ONE picture read as ONE surface is a clean, real
  relief (record/17: a face). Use: a grey-clay target beside a sculpt; detail from one view.

## What does not come out of it (why it is closed)
- PLACEMENT IS NOT LIKENESS: four blind block-ins of one goat gave four heads (can, slab, box, tapir). "right" in
  feature_report is place and size. The old 34-round hand sculpt was no further from the concept than any of them.
- A CHARACTER IS ONE FLOWING SURFACE. Everything below starts from separate parts or separate pictures and stays an
  assembly or a patchwork. Two pictures' accounts of one corner of a head lie 1-2 cm apart; the features are mm.

## Dead ends (each was built and rendered; pictures and slices in record/)
- More rounds of marks -> solids; a big part as several masses (worse: tapir head, rippled body).
- Forms as strokes for surface detail: clutter, not likeness.
- A picture's relief pressed into a block-in solid, part by part: tears on every part border (record/14, 15).
- Monocular depth: not used at all (docs/notes/measuremodels.md); only slopes, added up.
- Whole head as front + back skins joined at the outline: seam, ridge down the middle line; with the ears in the
  same surface the eyes are squashed (a 10 cm depth jump inside "one surface"). Record/16, 18.
- One depth gain for a whole read (anteater head). Pins at full weight on a finer grid (face folded: a pin's weight is
  per pixel AREA). A stiff-sheet bend to the outlines (wedge-shaped section).
- Sides from the outlines alone: ribs (a furry outline pushed through the head) and slabs (an eye's surround).
- Front, back and side skins: the side skin cutting everywhere (forehead cut, eyes pinched); standing away at points
  in a layer under the front skin (a lip like a mask's edge: record/seam_s17.png); the front skin lifted to the side
  skin's account (a fin along the rim). Best version: the side skin lifted as a height map (twoskin_agree.py), still
  a rough patchwork (record/21).
- `surfacefuse.refine` (Nehab et al. 2005) on the real reads: grain, twice (it passes on a rippled ball). A field made
  from refined points and normals: wrong sign beside thin edges.
- A horn as two skins with a flap's hem (a cushion with a flange); its root by carrying the outline into the head
  (blocky). Block-in rays through ALL the clay (the far horn is met first: one slab across the head).
- Fitting the block-in's solids to the reads: not built; ruled out by Joe (parts stay parts).

## Where things are
- Tools: tools_features.py, featuremap.py, featuresee.py, masses.py, masslines.py, forms.py, refread.py,
  guide_features.md. Reader: surfaceread.py. Tests: test_featuremap.py, test_masslines.py, test_surfaceread.py.
- The closed route is NOT on main: tag `archive/feature-map-closed-route` (relief.py, relief_press.py, twoskin.py,
  twoskin_build.py, twoskin_agree.py, surfacefuse.py, meshclay.py, tests/test_relief.py; each docstring lists what
  failed). The record's models with relief / twoskin blobs (scraps_r*, scraps_s*) build only from that tag.
- Record (durable): /mnt/data/hifipushie/featuremap/record/ = SCULPT_PROJECT.md (the whole history, sections 1-25)
  and pictures 10-21, seam_s17.png, horn_marks.png. Models: featuremap/home (scraps_five = the best blind block-in,
  scraps_s23 = where it ended). Reader: /mnt/data/hifipushie/measuremodels/surface (venv + weights, 6 GB).
- Ledger rows C450 to C455.

NEXT: nothing queued. Open housekeeping: featuresee.py is 678 lines (split the footprints out). Reopen only with a
way to make a character's surface WHOLE, as one thing: not from parts, and not by joining pictures.
