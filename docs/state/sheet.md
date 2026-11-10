# Sheet element (one seamless folded sheet): STATE 2026-11-10 (crush fold)

Branch sheet (worktree .claude/worktrees/sheet), from main d89f5709. Asked for by Baynard Racing (Puddles the pig,
gap 25 in baynard-racing/workspace/puddles/hifipushie_gaps.md). Not pushed; coordinator lands.

## What the tools hold now
- `sheet.py` (docstring = spec), wired into spec._compile, sdf.SDF, spec.SHAPES, expand_mirror, server SOLIDS.
  `{"shape": "sheet", "spine": [[x,y,z],...], "curve": "spline"|"bezier", "width_axis", "stations": [{"t",
  "half_width", "half_thickness", "cup", "twist", "puff"}], "root", "tip", "at"/"offset"}`. puff 0 = slab with round edges, 1 = lens (elliptic
  cross-section, thickest mid-width: clay, leaves), between = convex blend of the two estimates.
  - Spine: natural cubic spline through the points (chord length) or cubic Bezier controls (3n + 1).
  - Width axis: rotation-minimising (double reflection) from width_axis (default: the spine plane's normal), so a
    planar fold never twists; "twist" per station adds a deliberate one. Normal = tangent x width; .R mirrors flip
    "hand" so cup stays on the same side.
  - Field: nearest spine point (96-segment search + 4 Newton steps on the exact curve, straight past the ends) ->
    (s, w, n); core |w| <= half_width - half_thickness with elliptic end rounding ("root" / "tip" m), thickened by
    half_thickness (edges fully round). Exact through the thickness; |grad| 0.93..1.14 near the surface.
  - Refused: bend radius under the half thickness, half_thickness >= half_width, bad Bezier counts, straight spine
    without width_axis, end rounding longer than the sheet, unknown station keys.
- fit: `_sheet_parameters`: spine points under group "pos" (a centre-line sheet keeps x), stations' half_width /
  half_thickness under "size" (floored by MIN_SIZE; an invalid step is rejected as before). _get/_set take (row, int).
- tests/test_sheet.py: 19 tests (exactness, no knuckles: normal turns < 1.5 deg per step over the fold, RMF, mirror,
  twist / cup / puff, refusals, fit params).
- Cost: ~10 us per point (200k points 2.2 s); pud_sheet builds in 15-30 s at look resolution 256.
- softforms._natural now solves its tridiagonal system by Thomas (O(n)): the dense solve of a sheet's 255 knots
  took ~2 s each on a loaded BLAS (tests 4 min -> 18 s); same values (residual 1e-13), lofts unchanged.

## Proof (hifipushie workspace pud_sheet = copy of pud2, ear.L + earflap.L replaced by one sheet; pud2 untouched)
- Final ear (r12, ear_sheet_final.json): spine Bezier [0.082,-0.018,0.700] [0.092,-0.030,0.815] [0.160,-0.080,0.835]
  [0.170,-0.102,0.722] (root 3.5 cm inside the head, blend 0.03), stations hw 0.066/0.060/0.044, ht 0.020/0.020/0.016,
  cup 0/0.004/0.003, twist 0/6/12, puff 1, root 0.02, tip 0.04. Crops scale-matched to the references (zoom 4.3).
- Raking + curvature, front / side / three-quarter, beside the turnaround and concept crops: session notes folder
  sheet/ (ear_sheet_compare.png, review*.md). Curvature: one continuous rim band, flat faces, no line across the fold.
- Blind review (bin/review, 3 rounds): r10/r11 (slab) named a rope-like rim / "band across the bend" (the round
  edge seen as a tube; continuous in curvature) -> puff added. r12 (lens): no seam, band, plate or knuckle named;
  VERDICT FAIL on likeness only: the reference fold is closed and compact, its tip resting on the head (ours an
  open hook with a gap under it), the reference flap blunter / broader at the tip, rims still read crisp.

## Crush fold (branch crush-fold from main f3250f8c, 2026-11-10; Baynard gap 32)
- `"fold": "crush"` on a sheet: a bend tighter than the half thickness is built instead of refused ("round", the
  default, still refuses, and its message now names crush). Each over-tight bend (+ 2 half thicknesses either side)
  is cut into pieces turning <= 20 deg; `_nearest` searches one piece's u range and reports how far a point lies past
  an inner cut; sd_sheet = min over pieces, each capped flat at its cuts (hypot / max like a box end). A sweep is
  the union of its cross-sections, so the outside stays round and the inside fills to one crease.
- Ordinary sheets bit-identical to main (40k random points, plain + puff/cup/twist): no BUILD_VERSION bump.
- tests/test_sheet.py +6 (refused unless crushed; crush on a fine fold changes nothing; fat and hard folds: |grad|
  p1 > 0.85, p99 < 1.2 near the surface, no field jump within 8 mm of it, closed genus-0 mesh; the centre of the
  hardest bend is solid, the outside a half thickness out). Probe: jumps only >= 12 mm inside (the lens estimate
  deep inside, as on ordinary sheets at 29 mm).
- Proof on Puddles (Baynard workspace, not approved): a fat ear (half thickness 3.2 -> 1.6 cm, bend radius 2.7 cm)
  builds, fits the concept's outlines as well as the thin ones (clay off 78 cm2) and reads fatter and rounder; the
  ear's likeness is still Baynard's modelling stage.
- bin/suite fast tier: PASS (0 known failures; 16.5 min on a machine also running a fit).

## Open / next
1. Likeness is Puddles' modelling stage (Baynard side): close the fold (tip down onto the temple, less air under
   it), broader blunt tip, lower crown; maybe puff < 1 on the flap for a fatter rim. Not approved (tooling run).
2. The s-direction distance isn't corrected for (1 - curvature x n) on the fold's inside: fine for meshing; a blend
   against a sheet's inner fold reaches a little short.
3. Station cup / twist are not fit parameters (only widths and spine).

- bin/suite fast tier: PASS (0 known failures; 10.7 min, over its 10 min budget on a loaded machine).

NEXT: coordinator lands crush-fold (approval: Joe); then Baynard models the fat ear with it. Before: Baynard swaps Puddles' ear.L + earflap.L for one sheet (values above).
History: this page + commits on sheet; ledger row C372.
