# Eyes: lids, lashes, the eye surface (eyedetail, 2026-10-09)

The user, at Tess's front close-up next to her photo: "We also just don't seem to have the eye detail we need." He
pointed at the upper lid and crease, and at the lower lid. Branch `worktree-agent-a7cfe1a69c368b0db`. Scratch (DURABLE):
/mnt/data/hifipushie/eyedetail/:
- run.sh <script>: this worktree's src on the main workspace.
- run2.sh: run.sh plus likeloop / garrett4 / refstudy on the path.
- eyeshot.py <model> <tag> [json patch]: the face stage of a model (or a patched copy, `_ed_<tag>`) through the front
  reference's fitted camera under stage.FRONT_LIGHT. Writes out/<tag>_face.png, _eye.png, _eyeq.png (3/4), each as a
  reference | ours pair. LAYER=<paint layer> shows that layer's mask; CLAY=1 renders flat.
- strip.py: labelled judging strips.
- section.py <stage model>: a sagittal section of the scene meshes and lashes through eye.L.
- crease_diag.py / meshdiag.py: crease profiles through every stage of the pipeline.
- aperture.py: the 478-point detector's eye measures on eyeshot renders.
- gshot.sh <tag> [patch]: dressed Garrett (likeloop's mkd + garrett4's shot) measured by eyedbg (facesliders' copy).

## 1. Why the crease sliders didn't read (diagnosis)
- The groove survives every stage. eye_crease_depth 0.8 makes a +0.48 mm dent in the warped quads, the
  Catmull-Clark mesh, the IMLS field and the scene mesh alike. IMLS (kernel h 0.6 mm by the eye), meshing and
  normals (the scene's normals are the field's gradient) are not the cause. Sliders clamp at +-1.5.
- On Tess the groove lands on the fold's underside. Her platform is ~3 mm, and above it the surface faces DOWN about
  31 deg (N.L ~0.3 under FRONT_LIGHT, against ~0.93 on the platform). The template's crease height (6.2 mm over the
  margin) puts the dent in that shadow. A 0.5-0.9 mm Gaussian dent under a 38 deg soft key barely shades. The photo's
  crease is a fold over a tall lit platform.
- Routed: facesliders now places the crease from the head's own fold turn with a fold profile (main 9a18500, d772bbb);
  tess, her platform show.
- The ragged upper-lid margin was the face stage's 1 mm voxel. Fix: `scene.refine_box` / `parts.<p>.refine`. A box
  round both orbits (lids to brows) is meshed on its own 0.5 mm grid, projected onto the same field, and both meshes
  are cut EXACTLY at the box's faces and joined: no overlap, no crack wider than the chords' sagitta.
  skin_look.stage_spec adds the box for the head region (EYE_VOXEL, env HIFIPUSHIE_EYE_VOXEL; >= the stage voxel
  turns it off). Tess's stage mesh: 26 s at 1 mm, 48-70 s with the box, 110 s at 0.5 mm everywhere.
  - A first version overlapped the two meshes by a voxel. The lines seen round the box on Garrett were NOT that
    overlap: they are his own paint's creases (124_fold_shadow, cavity), identical with the refinement off
    (out/v_g78.jpg).

## 2. Lid margin thickness (faceslide.py, contained)
- GNM's lids taper to a ~1 mm rounded tip at the ball (out/v_sec.png). A real margin is a ~2 mm deep face, with the
  lash (anterior) edge in front of the waterline (posterior).
- `lid_margin_upper` / `lid_margin_lower` (0.9 / 0.8 mm at +1; one-sided; 0 = unchanged): the exterior skin moved
  forward along the eye's axis. Zero on the rim (the lid stays seated), full 0.7-2 mm out along the skin, gone by
  5 mm, faded at both canthi.
  - Splitting upper / lower by nearest rim vertex is ambiguous at the canthi. Without the fade, the step folded quads
    at +1.
- tests/test_lid_margin.py. test_faceslide passes (no fold at +-1, nor at 1.5: spikes/eyedetail/margin_fold.py).

## 3. Lashes (lashes.py, blender_lashes.py)
- How games do it: MetaHuman / AAA heads keep lashes as their own mesh, a few thousand triangles of strips along the
  margin, bound to the lid.
- Here each lash is one tapered ribbon (4 segments, width along the lid, opaque: no alpha to sort, sharp close up,
  sub-pixel coverage at a distance).
- Upper: 180 per eye, 9 mm, curl 68 deg, lift -6, flare 22 at the outer corner, clumps of 2-4.
- Lower: 42, 4.2 mm, finer and paler.
- About 2.7k triangles for both eyes.
- Roots: the lid lines are found geometrically (the opening seen along the head's forward axis, traced from its own
  centroid, not the ball's centre: Garrett's lids cover the ball's centre).
- Kept 0.3 mm off the ball and 0.15 mm off the skin.
- `base.lashes` = false | true | {upper, lower, color, lower_color, roughness, seed, segments}. ON by default for
  one-mesh humans.
- Scene: scene.sync -> job["lashes"] -> blender_lashes.show (object hp_lashes, key-cached).
- Painted lash line with geometry: only the roots' tone, a tapered tube through the lashes' own root curve
  (lashes.build "curves"; skin_features._hair). The margin-zone band it replaces painted the waterline and lid edge.
- Export: `lashes.export_part` (asset, after cloth): two-sided material (look "double_sided"), 16 px maps, the
  triangles subtracted from the low poly's budget (`lashes.triangles`). Face shapes: `lashes.shapes_from_lids` turns
  each lash rigidly about its eye's x axis by the angle its root's nearest lid vertex turns, plus the rest as a shift
  (faceshapes.apply, after the skin parts). Rig: Head (rig._head_kind).

## 4. The eye surface (skin.eyes)
- `gloss` (1): the tear film as a clear coat (coat 1, roughness 0.03) over a matte iris and sclera (roughness 0.4);
  scene via skin_features.eye_base merged into the eyes part's base; GLB KHR_materials_clearcoat. The catchlight
  reads sharp on the cornea's bulge.
- `occlusion` (1): eye_shade (under the upper lid) + eye_occlusion (a ~1 mm band all round where the lids lie on
  the ball, the corners darkest): MetaHuman's eye-occlusion shell as paint.
- `limbal`, `limbal_width`, `iris_contrast`; iris crypts (darker blotches between fibres, skin_swatch VERSION 15).
- Iris size, by the detector at the model's own scale (aperture.py): Tess's visible iris radius 5.0-5.1 mm against
  the photo's 5.36, eye width 23.5 vs 23.9: the iris / width ratio is within 4% of the photo (not too big, not too
  small). Pupil: Tess's spec has 0.3; the photo's bright light reads ~0.24 (tess's spec).

## Aperture vs paint (facesliders' measure)
- Garrett, dressed (likeloop mkd + garrett4 shot + eyedbg), mean opening of both eyes:

  | variant | opening (mm) |
  |---|---|
  | eyes-only paint | 7.30 (no lashes 7.11) |
  | dressed, before | 5.75 |
  | dressed, after the root-line lashes + keep-out | 6.37-6.45 |

- By skin group: zones / lips / roughness / micro -0.65, rims ~0, features -0.34. A 1.5 mm keep-out gained 0.08:
  not paint at the margin.
- The aperture's pixels are identical across eyes-only / +zones / dressed (out/ed_05_garrett_aperture_ge_gz_gd.png):
  what moves is the 478-point detector's lid points, which react to lid tints and wrinkles. Proposed: measure the
  aperture as visible eyes-part pixels.
- `skin._aperture_keep_out`: every skin layer but waterline / caruncle / lashes fades out within 1 mm of the eyeballs.
- Keep-out cost: a near mask on EVERY layer ran Cycles out of shader stack in the export bake (part:body). Now: the
  pre-composited layers get it (per vertex, free), and of the rest only eye-named layers, with "vertex": true. The
  lash root tubes are per vertex too. Tess's full export (procedural skin + lashes) bakes. Dressed Garrett
  (g4_garrett's ~30 hand layers + skin) overflows the stack even WITHOUT these (main's behaviour, measured on
  _ed_gx0): not mine, reported.
- The part-ID aperture (aperture.py, blender_scene job "id_parts"): visible eyes-part pixels, lashes hidden.
  Identical for eyes-only / +zones / dressed Garrett (5.12 / 4.85 mm, picture left / right), as it must be. Use it
  for the model's own opening (facesliders' lid-pose refit); the detector stays for likeness against photos.

## 3b. Export check (Tess copy _ed_tx with a mouth interior, 20k triangles, rigged, 5 face shapes)
- lashes part: 3552 triangles (180 + 42 per eye), two-sided material, Head 1.00 in the rig, 5 targets (blink max
  12.9 mm). The GLB posed with rig(glb=, shapes=): the lashes close with the lid (out/v_blink_eye.jpg).
- Lash defaults by body: men 12% shorter and 30% less curl; from 30 years fewer / shorter (by 70: -25% / -15%).
  Garrett (male, 52) reads as a fine dark line, not a comb.

## 5. Lower lid
- eye_bag 1 + eye_lidcheek 1 read: a bag with the lid-cheek crease's shadow under it, much like Tess's photo
  (out/v_lw.jpg). lid_margin_lower 1 gives a visible rim. Not set on Tess: her spec is tess's.

## Sheets
- out/ed_10_tess_eyes.jpg: photo | before | now | + lid margins, front face, eye, 3/4.
- out/ed_11_garrett_eyes.jpg.

## Still missing (blunt)
- No upper-lid crease / platform shadow on Tess: facesliders' crease rework plus tess's platform.
- The iris is still a painted disc: no refraction / depth, and the fibres read pale. A real cornea would be a
  transmissive shell over a recessed iris (MetaHuman's refraction): next if wanted.
- The lower waterline reads grey-blue (the ball's tear line + occlusion), not the photo's pink wet rim.
- Fine skin lines at the lids: not addressed.
