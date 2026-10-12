# hifipushie notes: headbody (how an untouched GNM head goes on our body: the join and the scale)

STATE (2026-10-12): Part 1 (measure) DONE: table + plain answer below. Part 2 (how others do it) DONE. Part 3 (design +
first build) IN PROGRESS. Branch `headbody` (worktree .claude/worktrees/headbody, from main 1ed30ce), not merged, not
pushed. Scratch DURABLE in /mnt/data/hifipushie/headbody/: env.sh, run.sh <script> (capped; heavy), light.sh <script>
(a light slot), out/. Scripts in spikes/headbody/. Models hb_*.
Part 3 step 1 BUILT: `base.head.attach: "native"` (onemesh.native / _native_desc / _neck_field / attach_report,
tests/test_headbody.py 5 pass); models hb_tess (from nt_N06), hb_garrett (from ng_N05).
NEXT: two meshes at export (the seam ring split), rig pose check, the sheets hb_01 / hb_02, an export run.

Joe, 2026-10-12: "that's some real work for us: how to get the body back on (and if we even want to, don't many games
leave them as separate meshes?) and how to match the size/scale of the head and body well." ... "let's get that
figured out."

## Part 1: where the head's size comes from (spikes/headbody/p1_measure.py; out/p1.json)

### Plain answer
- **0.846 is two numbers of OURS multiplied: 0.890 x 0.95.** 0.890 = GNM's template least-squares-scaled onto the
  head of Tess's MakeHuman body (the one mesh never uses GNM's size: `onemesh.head_desc` sets the head's scale to
  `bound k x io_scale`, the MakeHuman head's size, and `hook`'s gnm_base fits GNM's template INTO that head); 0.95 =
  her `base.style.human.head_size` (a block-in "head_scale" someone set). Nothing in it is a measurement of GNM.
- **Garrett's "1.12" is a dead key.** `base.head.scale` 1.12 is left over from the grafted path; `head_desc`
  overwrites it. His head is really carried at **1.039** of GNM's size = 1.009 (GNM fitted into his MakeHuman body's
  head) x 1.03 (his style head_size).
- So the gap between the two is 0.846 against 1.039 (23 %, not 15 %), and it is made of: MakeHuman's FEMALE head
  being 11 % smaller than its male head for the same GNM template (0.890 against 1.009), and two hand-set style
  factors pulling opposite ways (0.95 against 1.03).
- **Which side is wrong: MakeHuman's head is small, most of all the female one; GNM is real-sized.** GNM's class
  means are within 0-4 % of ANSUR II on every skull measure and exact on eyes apart and (female) face height.
  MakeHuman's female head is 5-12 % under ANSUR (eyes apart 55 mm against 62, sellion-menton 99 against 113), its
  male head 6-10 % under in the FACE (eyes 60 against 64, face 110 against 123) with a full-length skull.
  MakeHuman's bodies are drawn 7.9-8.0 heads tall (the figure-drawing canon); measured people are ~7.5.
- **What it did to the models:** Tess as built stands 9.0 heads tall with a 182 mm head (a real woman of 1.636 m:
  ~218 mm), eyeballs of 12.4 mm radius against GNM's 14.6, an 10.2 mm iris, eyes 55 mm apart. Garrett: 7.75 heads,
  a 229 mm head, 15.2 mm eyeballs (4 % over GNM's).
- **With GNM's head at its own size** (carry 1.0, same bodies): Tess 215.6 mm head = 7.6 heads at 1.636 m (ANSUR
  women: 7.5); Garrett 220.5 mm = 8.0 heads at 1.772 m (ANSUR men: 7.6; GNM's male mean head is ~5 % short of ANSUR's
  232 mm, and his identity sits at the class mean's size because the solve holds it there).
- Not to be confused with the solve's SIZE (gnm_atlas.md "### SIZE"): that is the identity's size INSIDE GNM's units
  (the face against GNM's fixed eyeball). The carry measured here multiplies everything, eyeball included. With the
  carry at 1.0 the iris check becomes a statement in real millimetres, which it is not today.

### Table (mm; same measure code on GNM's topology everywhere)
head_h = top of the skin to the chin landmark (ANSUR "menton to top of head"); breadth = skull's greatest width above
the eye line, ears left out; length = brow's front to the back of the skull; face_h = sellion (lm 27) to menton
(lm 8); ipd = eye centres apart. (My bizygomatic reader takes the cheek in front of the ear too and reads ~10 % wide
on every head: left out.)

| head | head_h | breadth | length | face_h | ipd | stature | heads tall |
|---|---|---|---|---|---|---|---|
| ANSUR II women (n 1986) | (218, ANSUR 1988, from memory) | 147.8 | 189.8 | 113.1 | 61.7 | 1628 | ~7.5 |
| ANSUR II men (n 4082) | (232, ANSUR 1988, from memory) | 154.3 | 199.5 | 122.6 | 64.0 | 1756 | ~7.6 |
| GNM template (its own units) | 215.9 | 155.6 | 193.9 | 114.4 | 61.7 | | |
| GNM female class mean | 213.8 | 153.3 | 196.6 | 113.5 | 62.0 | | |
| GNM male class mean | 219.6 | 157.0 | 203.2 | 116.9 | 63.4 | | |
| MakeHuman female 25, its own head | 199.2 | 138.0 | 181.1 | 99.4 | 55.2 | 1590 | 7.98 |
| MakeHuman male 25, its own head | 218.8 | 145.3 | 202.5 | 109.8 | 59.9 | 1730 | 7.91 |
| MakeHuman neutral 25 (the asset's reference) | 209.0 | 141.4 | 191.3 | 104.6 | 57.5 | 1659 | 7.94 |
| Tess's body (22, female, 1.636), its own head | 205.0 | 142.0 | 186.4 | 102.1 | 56.8 | 1636 | 7.98 |
| Garrett's body (52, male, 1.7715), its own head | 226.5 | 149.3 | 209.0 | 111.8 | 60.7 | 1772 | 7.82 |
| Tess nt_N06 AS BUILT (true base) | 182.5 | 131.4 | 157.6 | 99.6 | 55.3 | 1637 | **8.97** |
| Tess nt_N06, GNM's own evaluation of her identity | 215.6 | 155.2 | 186.4 | 117.6 | 65.3 | (1636) | (7.59) |
| tess_a1 AS BUILT (gnm_base 0.5) | 185.2 | 133.1 | 161.2 | 97.3 | 56.0 | 1643 | 8.87 |
| Garrett ng_N05 AS BUILT (true base) | 228.8 | 165.4 | 214.5 | 118.4 | 65.7 | 1773 | 7.75 |
| Garrett ng_N05, GNM's own evaluation | 220.5 | 159.3 | 206.6 | 114.1 | 62.3 | (1772) | (8.03) |
| garrett_a1 AS BUILT (gnm_base 0) | 236.5 | 156.7 | 225.6 | 116.7 | 64.2 | 1779 | 7.52 |

Carry (built head / GNM's own evaluation of the same identity; similarity scale over the hockey mask, and over the
whole head above the neck's hand-over):
| model | carry face / head | = s (MakeHuman head: bound k x io_scale 0.9365) | x gnm_base's fit | x style head_size | eyeball r mm |
|---|---|---|---|---|---|
| Tess nt_N06 | 0.845 / 0.846 | 0.909 (k 0.971) | 0.979 | 0.95 | 12.39 |
| tess_a1 | 0.824 / 0.827 | 0.909 | (half) | 0.95 | 12.60 (ours) |
| Garrett ng_N05 | 1.039 / 1.038 | 1.013 (k 1.081) | 0.996 | 1.03 | 15.15 |
| garrett_a1 | 1.029 / 1.059 | 1.013 | (none: MakeHuman's head) | 1.03 | 12.00 (ours) |

Sources: ANSUR II (Gordon et al. 2014, Natick TR-15/007) and ANSUR 1988 means computed from the public per-subject
tables at https://www.openlab.psu.edu/ansur2/ and https://www.openlab.psu.edu/ansur/ ; neck circumference 397.6 (men) /
329.8 (women), at the base 434.6 / 371.2; head circumference 574.4 / 561.1. "Menton to top of head" (ANSUR 1988
dimension 595) is NOT in the public tables: 232 / 218 mm are from memory of TR-89/044, to be checked before anyone
quotes them; the heads-tall column for ANSUR rests on them.

### How the one mesh sizes the head today (read from the code)
1. `onemesh.bound(params)`: every GNM skin vertex is bound to a point of MakeHuman's reference surface; a body of
   any age / sex / weight carries them. `k` = that head's size over the reference (neutral, 25) head's.
2. `head_desc`: `scale` s = k x io_scale, io_scale 0.9365 = MakeHuman reference eyes apart 57.79 mm / GNM template
   eyes apart 61.71 mm. Any `base.head.scale` in the spec is overwritten.
3. `hook`: the head = the MakeHuman-carried head + fade x (GNM's evaluation - GNM's template), all x s. With
   gnm_base 1 the MakeHuman-carried base is replaced by GNM's template x a least-squares scale onto it (Tess 0.979,
   Garrett 0.996) while the identity's difference stays at x 1: the face is NOT a similarity of GNM's evaluation
   even at gnm_base 1 (template and identity at scales 2 % apart on Tess).
4. `humanstyle.head_ops`: head_size scales it all about the top of the neck.
5. The neck: `neck_fade` hands the head's own shape over to the body's from the chin level down (10 rings at the
   throat, 20 at the nape); GNM's neck is not used.

### What GNM says (paper arXiv 2607.23687, repo google/GNM; our probes)
- Units: the npz is in METRES (template 0.341 m tall from the bib's edge to the vertex, eyes 61.7 mm apart, scleral
  radius 14.58 mm); the paper gives physical quantities in mm (limbus 6.0 +- 0.44, cornea radius 8.5 +- 0.73, scleral
  radius held ~14.6) but does not state the template's unit in the text read. Axes: Y up, face +Z.
- Extent: head, face, neck, eyeballs, teeth, tongue; "captures less of the torso than" FLAME-style models. The mesh's
  open edge is a BIB: x +-128 mm, down to 125 mm under the chin (y 0.066; chin 0.191; neck joint 0.134; head joint
  0.210; eyes 0.303).
- Joints: neck, head, left eye, right eye; linear blend skinning with artist-painted weights; no jaw joint (the jaw
  is in the expression basis). Nothing on attaching to a body; no body model named on the roadmap.

## Part 2: how others do it (research agent, 2026-10-12; URLs in the list)
- MetaHuman: face and body are SEPARATE skeletal meshes on one skeleton (the body leads; separate DNA files, per-LOD
  skin weights; head 8 LODs, body 4, kept in step by a LODSync component). A merge to one mesh exists
  (MergeHeadAndBody: keeps body joints, transfers face weights). By default the head's NECK region is blended to the
  body's seam; "Isolate Head From Body" keeps the head 1:1 with the source and leaves a visible seam. The body is
  parametric (height, "scale ranges by height"). Scale: "Align Scale" optionally scales an incoming head mesh to the
  body; with an authored seam the docs say alignment "None" (the head stays). Epic warns that large head / body
  proportion differences give a poor seam. Skin tone: one tone pushed to the body material as bias parameters and
  textures, the chest region of the face material updated to match.
  (dev.epicgames.com/documentation/metahuman: metahuman-dna-rig-definition-and-rig-operation,
  controlling-metahuman-levels-of-detail-lods-in-unreal-engine, metahuman-creator-from-template-tool-in-unreal-engine,
  metahuman-creator-body-params-tool-in-unreal-engine, body-conform-examples,
  metahuman-creator-from-custom-mesh-tool-in-unreal-engine.) Not found in Epic's docs: how seam normals are stored.
- Modular game characters: Unreal's Leader Pose component (child parts follow the leader's bones;
  dev.epicgames.com/documentation/unreal-engine/working-with-modular-characters-in-unreal-engine). Seams are split-edge
  vertices with different normals; the standard fix is custom normals TRANSFERRED to the seam vertices from one side,
  and identical skin weights (a mismatch pulls the head apart in motion): bg3.wiki/wiki/Modding:Fixing_neck_seams,
  wiki.bg3.community/Tutorials/Visual/Neck-Transplant, polycount.com/discussion/comment/2734308. Skyrim: every body
  variant must keep the SAME neck seam ring (nexusmods.com/skyrimspecialedition/mods/39704).
- Character Creator CC3+: the head's UV includes the neck, so the texture seam sits below the neck, not at the jaw
  (manual.reallusion.com Character-Creator-4 CC3-Plus-Characters). Daz Genesis 8.1 / 9: head and body are material
  zones / UV sets (single-mesh claim not verified).
- COPY: (1) two meshes on one skeleton with a fixed seam ring low on the neck, same count and positions on both
  sides; (2) normals and weights at the ring copied from one side, redone per LOD; (3) the head 1:1 with its source,
  blending only in the neck / on the body; (4) texture seam below the geometric neck line, one skin tone driving both
  materials; (5) a welded single mesh as an option. Nobody documents "the body proportioned to a fixed head": Epic
  scales the head or leaves it; we can do better because our body is parametric and our head is in real millimetres.

## Part 3: the native attach (built 2026-10-12)

### Measured before designing (spikes/headbody/p2_neck.py)
- GNM's neck is real too: girth at its narrowest (ring 19, ~1 cm under the chin level) 360 mm on the template, 334 on
  Tess's identity, 361 on Garrett's (ANSUR II: 330 women, 398 men); at ring 13: 374 Tess, 390 Garrett (ANSUR at the
  base 371 / 435). Tess's MakeHuman body (weight 0.15) has a 292 mm neck (296 at ring 13): 14-26 % under GNM's and
  11 % under ANSUR's mean; Garrett's body 361-385: equal to GNM's within 1 %.
- GNM's skin has 110-vertex rings from the bib's open edge (ring 0: 125 mm under the chin in front, shoulders 128 mm
  out) up to ring 25 under the jaw. The asset's stitch is ring 13: its front 55 mm under the chin (about the
  cricoid), its back 32 mm under the chin level (mid nape). Rings 0-12 (the bib) are not in our mesh.
- A blend in the neck cannot be right for Tess: GNM's neck at the jaw is thicker than her body's neck at its base
  (336 against 296), so any hand-over to the body's neck above the ring makes a neck that narrows downward. The
  body has to take the head's neck.

### Design as built
- KEY: `base.head.attach: "native"` (default "body" = the old path, bit-identical: hash test). `base.head.size`
  (default 1.0) = the head over GNM's own metres (a child or a stylised figure; not for likeness).
- HEAD: every GNM vertex from the seam ring up = GNM's evaluation (template + identity + expression, incl. the rest
  mouth's lip_close) x size, translated: `onemesh.hook` returns GNM's vertices moved by one vector. No MakeHuman head,
  no gnm_base fit, no dimorphism field, no style head sliders, no neck fade (`head_fade` = 1). Measured: max
  deviation from the similarity 0.0000 mm on 10,630 skin vertices (test: < 1e-9 m).
- PLACE: GNM's head joint (joint 1, the skull on the spine) on the body's skull pivot = where that joint lies when
  GNM's template is least-squares-fitted to the head the MakeHuman body carries (`_pivot`; skull + face, not the
  neck). The head therefore stands where the body's own head stood and grows / shrinks about the top of the spine.
- STATURE: the body's MakeHuman height is solved so the figure's top is the STATED stature (`base.body.height`, or
  MakeHuman's own for the age) under this head, style sliders (longer legs) included: Tess 1.636 -> body 1.601,
  Garrett 1.7715 -> 1.766. Figure stature exact to 0.5 mm (test).
- NECK: `_neck_field`: the body's vertices (MakeHuman's + the bridge) get the smoothest (biharmonic, cotangent
  weights) move that equals "GNM's vertex minus where the body would carry it" on the head and 0 beyond 11 cm over
  the surface from the ring (x stature / 1.7); the head's vertices are constraints two rings deep, so the surface
  keeps its slope across the ring. Then the rows within 4.5 cm are evened out ALONG the surface (GNM's ring is not
  parallel to the body's top loop; without it the bridge's rows were squeezed at the nape). Tess: 230-ish vertices
  move, at most 30 mm (shoulders / trapezius / clavicle pit widen to a 374 mm neck base); Garrett 34 mm (mostly along
  the surface: his girths agree).
- STYLE: body sliders still work; the head RIDES them rigidly (the pivot's move), and the neck field runs again on
  the styled body. Head sliders are ignored and named by `attach_report`.
- BONES: MakeHuman's head bones (head and its 59 children) are scaled about the pivot by size / (the body's own head
  size), so eye / jaw bones lie in the new head; the template's eye landmark and chin are GNM's.
- REPORT: `onemesh.attach_report(base)` (in `measure_human`'s text): size, head height, heads tall, eyes apart,
  eyeball, neck girth head / body at the ring, NOTES (neck mismatch > 12 %, heads tall outside 6.8 .. 8.3), ignored keys.
  hb_tess: 1.000 x GNM, 216 mm, 7.59 heads, neck 374 against the body's 290 (+29 %: NOTE). hb_garrett: 220 mm, 8.03
  heads, neck 390 against 384.
- Found on the way: `onemesh.template` raised AttributeError when `hifipushie.headfit` had not been imported by
  something else first (main too); fixed.

### Two meshes (built): `asset.head_body_meshes`, `write_glb` part "meshes"
- With `parts.body.topology: "wrap"` (the body's low poly = the fused quads; every vertex knows its GNM vertex) a
  native model's GLB holds mesh `head` (triangles whose three vertices are GNM's: skin, lids' loops, mouth sock) and
  mesh `body` (the rest: MakeHuman's + the bridge), both skinned to the one skeleton, same material / atlas. They are
  cut from the SAME corner arrays after uv, normals, tangents, bake and skin weights were made on the welded low
  poly, so the ring's vertices are written twice with identical position, normal, tangent, uv, joints and weights.
  Face-shape morph targets are on `head` only (53); `body` has none (the shapes fade to 0 at the ring: g_fade).
- `base.head.mesh: "welded"` = one mesh as before. A decimated body (no topology key) has no ring: one mesh + WARNING.
- hb_garrett export (rig, face shapes, 1024 px; 165 s warm): head 23,020 triangles / 11,566 vertices, body 19,020 /
  9,566, seam 110 vertices, largest normal difference across it 0.00 deg. Read back from the GLB
  (spikes/headbody/sheet02.py): 114 head vertices coincide with body vertices (110 places; 4 are uv-split copies),
  weights differ by 0; posed (Neck 15 + Head 30 about the vertical; Neck 20 + Head 15 forward): largest gap between
  the two meshes 0.00 um, largest normal difference 0.000 deg. No crack, no shading step: by construction.

### Where the ring sits, and what is NOT good yet
- The ring is the asset's stitch (GNM ring 13): in front ~55 mm under the chin (cricoid level), at the back ~32 mm
  under the chin level (mid nape). A buttoned shirt collar or a crew neck covers the front; an open collar or a
  t-shirt does not; at the back it stands ABOVE a collar and is covered only by long hair. It does not have to be
  hidden (positions, normals, uv and material are continuous across it), but for separate head / body materials or
  LODs it should sit lower: GNM has 13 more rings down to its bib (ring 8-10 = the neck's base, girth 457-511 mm,
  shoulders 76-86 mm out). That is a rebuild of the asset (spikes/onemesh/make_asset.py RING / C_RING, a new bridge
  onto MakeHuman's trapezius loop): NEXT, not done.
- NECK BEND / HEAD TURN: the SEAM holds (0 gap, 0 deg), but the neck's base CRUMPLES in both poses: jagged
  triangles in the bridge and the top of the trapezius. It is NOT the attach: the old path's export (gnmnative's
  ng_G00.glb, one welded mesh) crumples the same way, a little worse (out/seam_ng_G00_old.png beside
  seam_hb_garrett.png). Cause read from the GLB (spikes/headbody/wglb.py): the asset's own weights are smooth round
  the ring (largest step between neighbours 0.026), but the exported Head weight on the ring is 0.33 .. 0.97 with
  neighbour steps of 0.15 at the back (0.57, 0.77, 0.97, 0.96, 0.67, 0.54, 0.82, 0.96 ...): rig.py's rigid-head rule
  (floor under the jaw climbing to the skull's base at the nape, HEAD_FALL / HEAD_COLUMN falloffs) lays a Head weight
  on the nape rows that alternates vertex to vertex. Rig thread's to fix (rig.py `rigid_head`), on main as well.
