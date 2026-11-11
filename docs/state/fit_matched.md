# Fit to fitted cameras (fit_view.py, tool fit_matched): STATE 2026-11-10

LANDED on main 2026-11-10 (branch fit-part, Joe approved). Asked for by Baynard Racing (gap 33: no fit
of a part to a concept; Puddles' ears). Not pushed. Ledger C403.

## What the tools hold now (fit_view.py docstring = spec)
- `fit_matched(name, targets, only, params, lock, press, ...)`: fit.py's Levenberg-Marquardt (`fit.solve`, split
  out unchanged) on rows from fitted perspective cameras (fit_concept_camera), not just front / side / top.
  - OUTLINE target: a camera + box (+ mask; default the camera's image foreground): the whole silhouette.
  - FEATURE target (`elements`): that part's own outline traced in the picture (`outline` polygons in image px, or
    `mask`), against the pixels where the part is SEEN, in front of the rest (rays search its field only before
    the first surface hit). It sees a part spreading over the body or shrinking inside it; a whole outline can't.
  - PRESS (`press={"elements", "mm": 3, "join": [x,y,z]}`): the feature's surface buried deeper than mm, split
    into connected pieces; the piece within 1 cm of join (plus its depth inside) is the join, every other one a
    residual by depth. A buried tip changes no outline, so outline fits buried them.
- `fit.jacobian(prims_of=)`: rows sit on a chosen set of primitives (a feature's own field).
- tests/test_fit_view.py (3, 45 s): recovers a moved blob within 4 mm from a three-quarter camera; a part's seen
  outline changes 0.2+ IoU more than the whole silhouette when it sinks; press lifts a buried piece, keeps the join.

## Proof (hifipushie workspace pudfit: pud2 with Baynard's crushed ear refit; cameras concept / turn_front /
turn_side fitted on it, IoU 0.95-0.97)
- 10 targets (5 traced ear outlines + 5 whole outlines in the same boxes), only ear.L (spine + stations): 246 s
  (Baynard's workspace Nelder-Mead version: ~80 min). Ear IoU 0.83/0.81/0.80/0.79/0.59 -> 0.85/0.85/0.85/0.88/0.63;
  whole outlines unchanged (0.93-0.97); buried beyond 3 mm: 2.1 mm.
- Blind A/B (Baynard ab.sh, five matched tiles): beats d1 (the ear every earlier fit lost to); ties the crushed ear.
  Its MAJORs are form, not outline: the crush fold reads as a hard crease, edges bevelled, tip thinned to a knife
  edge (half thickness 16 -> 10 mm), no inner cup. Outlines can't see those; the fit shouldn't be asked to.

## Open / next
1. Side camera fitted at el -9.6 (Baynard's own fit: 0): its ear tile scores lowest (0.63). Check before trusting it.
2. A FORM row (shading or normals against the picture) is what's missing for likeness; not started.
3. press takes one join point; two symmetric parts need one target each (or a list: not built).

NEXT: Baynard fixes the ear's form (crease, rim, tip thickness) by hand.
History: this page + commits on fit-part; ledger C403.
