# Mouth loops (edge loops round an opening modelled into a part, no template): STATE 2026-11-05

Landed on main 2026-11-10 (built on limb loops, C375; this run 2026-11-05). Step 3 of
the creature-topology project, asked for by Joe through Baynard Racing (Puddles' open mouth). Exploring run (no gate).
Ledger C405. Limb part of the thread: docs/state/limb_loops.md.

## What the tools hold now (mouthloops.py docstring = spec)
- Any subtracted blob of a `topology: "limbs"` part that breaks its skin is an opening (a mouth, a beak's gape):
  `mouthloops.openings`, called by `limbloops.build` as one more feature beside the limbs. General: no names.
- Cavity = the skin that exists only because of the cut (CAVITY_DEPTH 2 mm inside the part without it); its edge on
  the fine mesh IS the rim, wherever it runs (Puddles' gape is wider than the muzzle and wraps round its sides: no
  flat section across it walls all round; the first, section-based try found no rim). Ring count = rim perimeter /
  the part's edge length (even, 16..48: Puddles 36-38). Rim respaced by arc length; OPEN_WALLS (6) rings walked
  across the surface toward the cavity's back until they close up, a fan of quads at the last ring's centre;
  OPEN_JUNCTION (2) border rings walked out over the face, relaxed / untangled with the body (fixed, they folded in
  the crease under the lower lip). Cut (inside the outer ring, shallower than the back + 2 steps), zip, decimate
  with the rings as border: as a limb's.
- `limbloops.quality(loops=)`: a ring by its own vertex ids (a closed quad edge loop through exactly them): an
  opening's rim needn't be flat, so no plane test. The export's topology npz now records the key rings ("rings",
  json) and an opening's rim / wall faces are kept under other parts (teeth against the upper wall: the hidden drop
  broke walls 1-3, and they would show as holes once the mouth moves).
- tests/test_mouthloops.py (1 test, ~3 s): round head on stub legs with a wide cut; rim + 2 walls closed, mesh closed.

## Proof (workspace pudmo = copy of pud2 + topology "limbs"; /mnt/data/hifipushie/mouthloops, renders also in the
Baynard notes folder mouth_loops/)
- Model build: rim + walls 1-5 closed quad rings of 36 (wall 6 feeds the fan: not a loop by design); field 0.08 /
  0.6 mm; turned faces round the mouth 2 (both at the hidden back fan). m1.png (wire: new top, today's below).
- Export (pudmo.glb, export_asset(rig=True), body 12.8k tris): limbloops.quality on the exported topology by its
  recorded rings: rim + walls 1-5 closed rings of 38, hips 16 (8/9; wall 6 = the fan's). Before the hidden-drop
  exemption walls 1-3 were broken under the teeth.
  Within 8 cm of the mouth: 0 turned, 0 folded triangles (today's pud2.glb also 0: its rim was already clean at
  rest, the old kit-mouth tangle is gone from v11). GLB close-ups front / three-quarter beside pud2.glb: the same
  clean rim and dark walls; ours shows two faint shaded lumps on the back wall (the fan) through the opening.
  glb_mouth_today_top_new_bottom.png, glb_mouth_wire_today_top_new_bottom.png.

## Open, ranked by what shows in the kart
1. The back fan (36-38 spokes) shades as lumps seen through the open mouth: close the back with a grid patch (or
   stop the walls earlier and cap flat) instead of a pole.
2. Body-wide export warnings with "limbs" (13-18 folded edges, max error 6.5 mm, 1 non-manifold edge): not at the
   mouth (0 there); find them (likely the leg tips inside the hooves) before Baynard ships it.
3. From limb_loops.md: crotch patch (the GLB front read worse), torso / head rings from loft sections and the head
   ball, shoulder / neck junctions, eyes / snout loops, sheet ears and tails as tubes, weights smoothed along rings,
   a quad-remesher fallback for shapes that aren't limb-like.
4. A jaw: an opening's rings are where a jaw bone's weights should split (upper / lower lip); not rigged here.

## Dead ends
Rings in planes across the opening's axis (a gape wrapping round the muzzle has no walled section: no rim found);
the fan's tip at the axis' point on the back wall (off the last ring's middle: its quads turned).

## Commands
`/mnt/data/hifipushie/mouthloops/{dev.py <model>, wire.py, glbmouth.py, glbq.py, topoq.py, export.py}`

NEXT: the crotch patch + the back-of-mouth cap, re-export, judged on
the GLB front and through the open mouth.
