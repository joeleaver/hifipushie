# STATE: texture repaint (texrepaint_*), 2026-11-17

Branch claude/texture-repaint-f66329 (not landed; the director's OK first). Guide: guide(topic="texrepaint")
(src/hifipushie/texrepaint_guide.md). Outputs on /mnt/data/hifipushie/texrepaint/<mabel|scraps|hettie|kart_scraps>/.

## What exists
- Tools texrepaint_start / _regions / _paint / _look / _face / _decal / _render (tools_texrepaint.py); steps in
  texrepaint_run.py; surface (texels as 3D points, blur across seams), concept (turnaround split + registration by
  colour agreement), regions (materials, zones, contradictions), paint (4K colour / normal / roughness, material
  detail in 3D), decal (face, rectify, redraw from concept corners). tests/test_texrepaint.py (8, synthetic, fast).
- Run inputs: examples/texrepaint/materials.json + keep.json (the painter's decisions per character).

## Results (judged by eye beside the turnaround)
- Mabel: good. The invented black back is cream with the turnaround's two spots; eyes, nostrils, mouth kept.
- Hettie: good-ish. Mostly one cream (low risk); side panel registration is offset (her side figure is wider).
- Scraps (round 2, director-approved run, maps in oxidegen retopo/scraps/repaint/): eyeball yellow + canister red are
  `ignore` materials (other parts the art shows in front of the face), horn zone z>0.88, nose paint set from the
  concept, lip crevice brushed cream, the art overrides only design-sized (>= 20 cm2) disagreements, blur 1 % of height.
  Front face now reads (white blaze, dark eye rings, pink nose and ear insides); side of the head still somewhat camo-
  patchy, back warmer than the concept's grey with a few cream flecks.
- Kart sign: the pictogram is redrawn cleanly from the concept (4 flat colours). Its UV island is ~300 px at 4K, so the
  sign is clean but soft at close range.
- The kart's other parts are the generated atlas upscaled (no region pass yet). The kart GLB has a stray 1 m Icosphere (hidden in renders).

## Open
- Scraps' face: needs zones or a "face" material (cream face, charcoal eye patches) and horn zones (z > 0.85).
- Registration: a matte option for patterned backdrops; side/back offsets.
- Hard-surface region pass for the kart (metal de-lighting, paint, rust, wood); the sign back is unseen (kept as generated).
- The image-model path for graphics (oxidegen edit) is wired as decal(graphic=...) but has not been run.
- bin/suite was NOT run; only tests/test_texrepaint.py.

NEXT: Scraps' side-head patches (a face material with zones, or a cooler taupe), check Hettie's front-head red, run bin/suite, then ask the director whether to land.
