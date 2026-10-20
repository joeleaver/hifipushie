# STATE: cloth_release (worn open = closed fit + ONE release sim) -- 2026-10-20

What: a garment designed to be worn open is fitted CLOSED on the dress form (pattern_form, top button fastened), then
ONE short sim started from that fit lets the closure go (Joe 2026-10-20). Module src/hifipushie/cloth_release.py
(docstring = spec), MCP `release_garment(name, garment, release=["front"], submit=False)`; fit_garment's next step
points to it when the garment has worn_open. Test tests/test_cloth_release.py (KAT with HP_RUN_ZOZO=1, local ZOZO).

## The job (cloth_release.job)
- start = the fit; membrane rest = flat pattern (zozo rest "flat"); bending flat, fold lines folded
  (folds.bend_reference), made pieces as fitted; every seam + non-closure stitch sewn; `release` closures not.
- held (carryIdx, pinned as fitted all sim): the neck's made pieces (stand, collar: neck_pieces). The shirt collar
  under a jacket collar is a fold over a fold: 1144 edge pairs within 2 mm that no press parts.
- start made clean (each step reported in info): shoulder pad (when the fit used one) pressed under the garment,
  never below the body (pad_base); the garment's vertices off the body (vertex-only, <= 4 mm); the under garment
  pressed under to 3.5 mm along its normal, at most down onto the body; its faces no press parts dropped from the
  collider (Garrett: 244 at armholes / neck); last edge pairs stepped off <= 2 mm.
- schedule 24 fps: sew 4 (gravity 0) + settle 48 (2 s) + self_settle 24 (1 s). Garrett: 2 s is within 2 mm (p90) of
  a 6 s settle; one spot (front.R waist) still moving 9 mm / 6 frames at 3 s.
- preflight: cloth_job.preflight (now reads rest / start_over from the zozo dict). A start whose strain is over the
  limit on > 3 % of triangles needs zozo start_over (Garrett 5.2 %: start_over 0.06): a FIT fault, report it.

## Known faults of the method (NEXT)
1. Seams open 1-4 mm after the sim (white lines in renders): the runner steps coincident seam ends apart (stitch_gap
   2 mm) and 4 frames don't close them. Try stitch_gap 0.0005 / sew_frames 12 locally first.
2. Made flaps (pocket flaps) aren't held: they sag 16-19 mm.
3. The KAT proves the mechanism (opens vs a buttoned control, chest stays, settles), not a magnitude: a coned front
   can't hang plumb isometrically (cylinder 10 mm, symmetric cone 15, oblique cone 21 mm).

## Cost / runs
Local ZOZO (ROCm iGPU) runs a 7.9k-vertex jacket at ~1.3 s / frame (76 frames ~2 min): prove settings locally, rent
only the run that counts. Rented (oxidegen bundle): 47 s GPU, $0.0355.
History: docs/notes/cloth.md "fit round 16".
