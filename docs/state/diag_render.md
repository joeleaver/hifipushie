# STATE: diag_render (diagnostic construction renders)

STATE: built 2026-10-19 on branch diag-render (worktree agent-a44ee644ff0cc4f34), committed locally, not on main.
NEXT: coordinator lands it; construction reviews add the diag sheet beside clay (gates.md LOOK); optional
bin/judge shots `--diag` (not done: judge renders GLBs in blender_game, it would need the pattern mesh carried).

## Current best
- `src/hifipushie/diag_render.py` (Python side) + `blender_cloth._render_diag` (EEVEE, emission per corner, Backfacing
  mix, Standard view: PNG pixel = declared sRGB). Clay default untouched (`cloth.render` without `diag`).
- Call: `cloth.render(objs, prefix, views, diag=[modes])` (legend -> `<prefix>_legend.png`); `diag_render.sheet(rows,
  out, modes, views)` (rows `(label, objs[, {"diag", "box"}])`, one panel colouring across rows); `pattern_sheet_diag`.
- Single views: sheet keeps `<stem>_r<row>_<view>.png` + `<stem>_legend.png`; reviewers get ONE view per turn.
- Garment objects carry `"mesh"` (pattern mesh dict) and `"layer"`; others (body) render flat BODY.
- Modes: panels, seams (dark tubes; dashed yellow fold lines), turned (orange shown side / dark brown other side;
  the shown side is read from the base's outward winding vs the body), backfaces (red), strain (+-10 %), layers
  (layer colours, inner-through-outer magenta via garment_game.crossing_faces + behind-ray test).

## Proof
- tests/test_diag_render.py: measures (pure) + 13 pixel checks (two panels/seam/turned flap; 10 % strip red only;
  inside-out red; poke magenta). Renders: /mnt/data/hifipushie/diag_render/known/.
- n8: /mnt/data/hifipushie/dress_garrett/pattern_stage/n8_diag_construction.png, n8_diag_strain_layers.png
  (script n8_diag.py there; read-only on form2/asm_n8_*.pkl).

## Findings on n8 (for dress-garrett)
- Side-neck shoulder-seam corner: seam lines knot into a loop at both side necks; the collar shows its other side
  (dark brown) in a strip from the side neck down; strain map: blue crumple beside red stretch at the same corner.
- Shirt through jacket: 818 shirt faces magenta (underarms / back armholes, sleeve undersides).
- Jacket strain p99 54 %, p50 3.8 %; shoulders saturate red (> +10 %).

## Open
- Panel colours: 16-colour palette, >16 pieces reuse colours on non-sewn pieces (legend disambiguates).
- Strain + backfaces together: both use red; don't combine (legend says which).

## Dead ends
- (none yet)

## History
- docs/notes/render.md "## Diagnostic renders"; codified.md C13.
