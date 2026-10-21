# Shirt spike (2026-10-21): Simon's shirt on the average male, closed and worn open, no sim

Thread page: docs/state/collar_spike.md. Ledger: docs/notes/codified.md C137-C140. History: docs/notes/cloth.md
"shirt spike 2026-10-21". Outputs (pkl / png) live on /mnt/data/hifipushie/shirt_spike/ (not in the repo).

Body: workspace model `wf_simon` (MakeHuman 35 y, 1.78 m, weight / muscle 0.5) with its Simon shirt design.

## Scripts (run.sh <script> [args]: this worktree's code under bin/capped; edit run.sh's cd for another checkout)
- `base_fit.py <tag> [json]`: pattern_form.on_form (the no-sim fitter), ~15-27 s, writes <tag>.pkl + clay / diag
  renders. The json hooks (`kb_folds`, `roll_angle`, `simon_seam`, `band_ends`, `collar_roll`, `from_garrett`,
  `OPEN_SPREAD`, garment keys) were the in-memory test harness for the fixes now LANDED in the repo; with the
  landed defaults `base_fit.py v0 '{}'` gives the fixed closed collar. Concept button: `{"closures": [{"name":
  "front", "spacing": {"first": 0.034, "from": "cfNeck"}}]}` (first fastened button 83 mm below HPS on wf_simon).
- `flatarap.py <from> <out> json`: the OPEN state by staged per-face ARAP against the FLAT pattern (Liu 2008 local /
  global, sewn pairs welded, bending free). `pts`: [apart, below HPS, stand-off] collar point targets; `swing`: deg,
  each band end swung about Simon's hinge ruling; `steps`. `kb` / `kb_pieces` (hinge-spring bending) DIVERGES on
  the collar / stand: open bug.
- `openarap.py`: staged ARAP with the closed fit as rest (edge / roll handles). Superseded: a closed-shape rest can't
  open the collar ring.
- Reads: `sym.py` (mirror symmetry per piece; floor = mesh spacing), `faults.py` (per-piece strain / inside / open
  seams), `csec.py` (collar sections round the neck), `cbprof.py` (the CB section walk), `openm.py` (open reads vs
  the concept; its V read is broken), `draftinfo.py` (what our pipeline changes in Simon before the fit).
- Renders: `crops.py <tag>` (REG=collar | throat | default faults; DIAG=strain or panels,seams,turned), `sheet.py`.

## What was found and landed
- C137: collar / stand meshed at 2 mm (FORM_REFINE_SHIRT): at 5 mm the 3 mm roll turned as two kinks + a shelf.
- C138 / C139: the KB no_tie open-neck rolls (L / R declared differently, and turning the neckline the band is sewn to)
  removed; Simon's band sewn EDGE TO EDGE onto the placket tops and its drafted ends kept (cloth_designs simon
  `band_ends: false`): the band's end continues the front's edge (Joe's photos).
- C140: pattern_form._turn_flaps picks the further-outside sense among those near the asked turn (FLAP_OUT_FIRST).
- Mirror rule (every bug of the day): a SIDE is taken from a landmark well off CF (a hinge, a neck point), never
  from a point at CF, where the band's ends cross.
