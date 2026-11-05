# Soft primary forms (loft, super): STATE 2026-11-04

Branch loft-super (worktree .claude/worktrees/loft-super), from main 5e840ded. Asked for by Baynard Racing (Puddles
the pig, gaps 11 and 14 in baynard-racing/workspace/puddles/hifipushie_gaps.md). Not pushed; coordinator lands.

## What the tools hold now
- `softforms.py` (docstring = spec), wired into spec._compile, sdf.SDF, spec.SHAPES (csg / deform / hollow apply).
  - `"shape": "super"`: |x/rx|^n + |y/ry|^n + |z/rz|^n = 1, "squareness" (one n, default 3) or "exponents" [nx,ny,nz],
    1.2..12. n = 2 equals the ellipsoid exactly outside it. Distance estimate (G-1)/|grad G|, G = F^(1/min n).
  - `"shape": "loft"`: "sections" [{z, half_width, half_depth, squareness 2, offset_y 0}], z rising, local z
    (rot turns it); natural cubic splines (C2) carried straight past the end sections; caps "top"/"bottom"
    {z, round 3} as the superellipse rho^r + t^r = 1 (well scaled to the tip; round >= 3 keeps C2 at the cap start).
- fit: group "shape" (squareness) added to GROUPS; a loft's section half sizes ("size"), offset_y ("offset"),
  squareness ("shape") and cap z ("size"). Params index (section, key) / dict key; changes listed one per value.
- fit(init_loft=<blob>) / fitmod.loft_from_refs: sections measured off front/side outlines; a value the outline
  would move > 25 % is kept and said ("another part?": arms, snout cross the outline).
- fit no longer crashes when a step or a Jacobian nudge makes an element invalid (blade at its thickness limit):
  the step is rejected / the difference taken backwards. Found on pud's ears in the full fit.
- server SOLIDS (kit_reference) describes both shapes. tests/test_softforms.py: 12 tests.

## Proof (hifipushie workspace; renders in the Baynard notes folder, see below)
- pud_loft v8: pud with body + waist + head blobs replaced by ONE loft from the brief's measured sections, then a
  full fit: IoU front 0.976, side 0.963. pud_blobs v2: copy of pud, same full fit: 0.973 / 0.965. pud untouched.
- Raking light: blobs show horizontal grooves z 0.42-0.6; loft none. Blind review (bin/review, a = loft, b = blobs):
  bands named MAJOR on b front and side, none on a. Profile curvature test: loft jumps < 5 /m per 2 mm step, a
  rounded box > 1000.
- Review also FAILED both on likeness, equally: no separate big head with cheek overhang, flat crown, lumpy back
  line, base tapering into the legs. Those are the section values / Puddles' modelling stage, not the primitive.

## Open / next
1. Curvature render shows a thin warm line at the belly's widest section (z 0.245): the surface is C2, its curvature
   a tent peaking at the knot (measured); the render colours the field's Laplacian, which also jumps there. A C3+
   interpolant (quintic) would round the peak if reviewers keep reading it as a line.
2. fit barely moves squareness (Jacobian small next to the prior at max_step 0.02); give "shape" its own step.
3. Puddles' head-and-body proportions (Baynard side): re-measure sections from the turnaround with the head as the
   largest volume, top round ~2.5, then fit. Approval of pud_loft not asked (tooling run).

NEXT: coordinator lands loft-super after bin/suite; Baynard rebuilds Puddles' mass as a loft.
History: this page + commits on loft-super; ledger row C370.
