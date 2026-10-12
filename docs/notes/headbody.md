# hifipushie notes: headbody (how an untouched GNM head goes on our body: the join and the scale)

STATE (2026-10-12, round 3, NECK FIX BUILT after Joe's "Yes, go on the neck fix"): the head is seated by its OWN neck
base (GNM's bib fitted on the body's shoulders) and the body's neck base / shoulder slope is laid ON the bib next to the
ring, fading into the body's own shoulders; no pull-down, the ring stays, two meshes with matched open edges. General
rule, nothing per character ("Bodies should just work"): run untouched on 10 bodies with class-mean heads. Sheets
workspace/human_renders/hb_05_neck_fixed.png (REFERENCE | NOW | previous native | old; rest x 4 views + two poses),
hb_06_figures.png, hb_07_body_range.png. attach_report carries the anthropometric checks and flags. Tests:
tests/test_headbody.py 6 pass (incl. the body range), old path hash unchanged. Details: "## Round 3" at the end.
VERDICT (mine, blunt): the necks now READ AS NECKS at rest and in both poses (short, a shoulder slope that starts
under the ear, no column, no shelf, no crumple). Not good yet: no SCM / clavicle / throat-pit definition (smooth
forms only); women get GNM's thick class-mean neck (363 mm) on MakeHuman's thin-necked bodies: a bull neck, flagged;
a very tall body gets an average head + neck (flagged); Tess's upper back still ripples (MakeHuman's, old attach too).
NEXT: the solve needs a neck-girth read / prior (women's class mean is +11 % over ANSUR, and head_000 / head_001 move
it unread); neck surface forms (SCM, clavicles) as a skin-folds / anatomy matter; a lower ring only if separate
materials need it; rig.py head-weight smoothing NOT needed after the faceshapes fix (posed tiles clean).
Branch `headbody` (worktree .claude/worktrees/headbody), main merged in (7c6909d), not pushed. Scratch DURABLE in
/mnt/data/hifipushie/headbody/ (env.sh, run.sh heavy, light.sh, t1.sh pytest, out/, ansur/, export_*).

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

### Consumers: what works, what must change (checked 2026-10-12 on hb_garrett / hb_tess unless marked)
| consumer | state on a native head |
|---|---|
| build / look (base.surface: one IMLS field over the fused quads) | works unchanged (one field; the split is an export matter) |
| export_asset GLB, rig, face shapes | works: two meshes with `parts.body.topology "wrap"`; one mesh + WARNING when decimated. FBX (blender_fbx reads the GLB) NOT run |
| rig.py (Mixamo) | works: Neck / Head / HeadTop_End from the template's joints (HeadTop_End 1.773 = stature); weights by index, identical on the ring. The rigid-head rule's nape zigzag (above) is the open fault, old path too |
| faceshapes | works: 53 targets on `head`; GNM's deltas x g_fade (0 at the ring), so the ring never moves and `body` needs none. Simpler than before: shapes are x 1.0 of GNM's (the old path multiplied by the carry ~0.85-1.04 and head_size) |
| eyes (base.eye_native, drawn_iris, iris_check) | simpler: GNM's eyeball at its real size (r 14.6 mm, limbus 5.99 -> iris 12.0 mm); the iris check is now in real mm |
| measure_human / humanfit | works; prints the attach report. fit_human's body solves and `nudge` not exercised on a native head |
| blockin / block_in_solve (NOT touched: the solve agents') | MUST CHANGE: a model's fitted cameras are for the old head's size and place: refit after switching (cameras "refit"). `block_in_step head_scale` (= base.style.human.head_size) and `gnm_base` / `dimorphism` steps do nothing on a native head (reported as ignored, not refused): they should refuse, or head_scale should set base.head.size. `block_in_start` still writes attach-less bases: making native its default is a one-line change there, Joe's call |
| hair | must be regroomed: the scalp is 4-18 % larger / elsewhere (mk.py drops hair). Seating reads the built head: no code change expected, NOT run |
| cloth | collars / necklines: the body collider is the built body, so a draft made to measure follows the thicker neck; garments sewn on the old neck must be re-simulated. NOT run |
| skin paint / textures | one part, one atlas, one material across the ring: continuous by construction (uv not split at the ring unless a chart border falls there). Separate head / body materials (MetaHuman-style) would need the tone matched and the ring as a chart border on both: not built |
| retopo | `base_quads` (the fused quads) is the path; the template wrap ("template") is not used for one-mesh humans |
| style sheets (humanstyle) | body sliders work (the head rides rigidly, the neck field reruns); head sliders are ignored: a stylised head on this path = `base.head.size` + GNM identity only |
| LODs | none yet: when built, the ring must survive (decimate head and body separately with the ring's vertices locked) |

### Decisions for Joe
1. Make `attach: "native"` the default for new humans / block_in_start? It is what "GNM's own head" means in full
   (shape AND size); it changes every figure's proportions (Tess 9.0 -> 7.6 heads) and needs cameras refitted.
2. Tess's neck: GNM's neck for her identity is 374 mm at the ring (ANSUR women at the base: 371), her MakeHuman body
   (weight 0.15) has 290. The body now gives (shoulders widen at the neck's base). It reads as a strong neck on
   narrow shoulders. Either accept, or raise the body's weight / muscle a little, or let the SOLVE read the neck
   (nothing reads it today: it is the class mean's).
3. Garrett stands 8.0 heads tall with GNM's 220 mm head (was 7.75 with 229 mm): GNM's male class mean head is ~5 %
   under ANSUR's and the solve holds size at the class mean. If he should have a bigger head it is a statement about
   the identity's size (the solve's "iris" / a size prior by sex), not about the attach.
4. Lower the seam ring (rebuild the asset at GNM ring ~9, on the trapezius)? Needed only for separate materials /
   LODs or if the ring must hide under every collar.
5. Two meshes by default (as built) or welded by default?
6. The rig's rigid-head rule at the nape (crumpled neck base on head turn / neck bend, both paths): a card for the
   rig thread.

## Round 2 (2026-10-12): the neck. Measured, diagnosed; fix proposed, NOT built (gate)

### Anthropometry used (ANSUR II, computed from the public per-subject tables; /mnt/data/hifipushie/headbody/ansur/)
| measure | women (n 1986) | men (n 4082) |
|---|---|---|
| top of head - suprasternale (stature - suprasternale height) | 298.8 +- 13.6 mm = 0.1836 of stature | 317.6 +- 14.4 = 0.1809 |
| top of head - cervicale | 232.8 +- 11.9 | 238.9 +- 12.9 |
| top of head - acromion | 293.4 | 315.5 |
| tragion - suprasternale / - cervicale (stature - tragion-to-top - ...) | 172.3 / 106.3 | 186.5 / 107.8 |
| neck circumference / at the base | 329.8 +- 19.2 / 371.2 | 397.6 +- 25.8 / 434.6 |
Chin (menton) height is NOT in ANSUR II: "chin over the pit of the throat ~81 / ~86 mm" = the rows above minus the
head heights 218 / 232 FROM MEMORY (ANSUR 1988). Landmarks on our meshes: suprasternale = MakeHuman body vertex 1522
(front midline pit between the clavicles), acromion = vertex 8275; both are below the neck loop, in every build.

### Neck length (spikes/headbody/p5_necklen.py; mm)
| figure | head (top - chin) | chin over the pit | top over the pit (/ stature) | GNM's OWN chin -> its own pit (bib) |
|---|---|---|---|---|
| ANSUR women / men | 218 / 232 (memory) | ~81 / ~86 | 299 (0.184) / 318 (0.181) | |
| Tess old attach nt_N06 | 182 | 74 | 257 (0.157) | |
| MakeHuman's own, Tess's body | 206 | 75 | 280 (0.171) | |
| Tess PREVIOUS NATIVE hb_tess | 216 | 85 | 300 (0.184) | 73 |
| Garrett old attach ng_N05 | 229 | 90 | 318 (0.180) | |
| MakeHuman's own, Garrett's body | 227 | 90 | 316 (0.179) | |
| Garrett PREVIOUS NATIVE hb_garrett | 220 | 102 | 323 (0.182) | 84 |
- In TOTAL the native stack is anthropometric (top over the pit 300 / 323 against ANSUR's 299 / 318): the stature
  solve did not stretch anything. What is long is the NECK inside it: the chin stands 85 / 102 mm over the body's pit
  where GNM's own neck (its bib has a pit of the throat: 73 mm under the chin on Tess's identity, 84 on Garrett's,
  71 on the template) says 73 / 84, the old attach 74 / 90 and ANSUR ~81 / ~86. So the head sits 12 mm (Tess) / 18 mm
  (Garrett) too high over the shoulders. Cause: the pivot rule put GNM's skull where MakeHuman's skull was; GNM's
  neck is shorter than MakeHuman's from skull to pit, and Garrett's GNM head is 9 mm shorter than his MakeHuman head
  with the top held by the stature.

### Why it reads far taller than 12-18 mm, and lumpy (one cause; out/neck_overlay.png, out/gnm_bib.png)
- GNM's own neck is SHORT and clean: its trapezius leaves the neck right under the ear (side silhouette, template:
  half width 57 mm down to 16 mm under the chin level, 61 at 22, 68 at 27, 76 at 32, 97 at 44, 128 at 58). All of
  that slope is in rings 0-12, the BIB, which our mesh cuts off at ring 13.
- The asset's ring A is not where GNM's ring 13 is: when the one mesh was made the lower rings were SLID up
  MakeHuman's neck (21 mm above loop C all round) to make room for the bridge. With the heads coincident GNM's true
  ring 13 lies ~25 mm lower than that bound ring, i.e. ON MakeHuman's trapezius / in the bridge's zone.
- `_neck_field` is a displacement field: to bring the bound ring to GNM's ring it moved the bridge AND MakeHuman's
  trapezius rows 25-30 mm DOWN (and out). Result in the front silhouette: the neck's column runs straight down
  40-45 mm further than on the old attach or on MakeHuman, then turns a corner into a near-level shelf (Tess: corner
  ~15 mm above the pit; MakeHuman's slope starts ~60 mm above it). That shelf + corner is the "lump"; the extra
  column is the "way too tall". Back view the same: a long nape on dropped shoulders.
- Not the cause: the stature solve (total stack right), GNM's neck girth as such.

### Tess's thick neck (item 3): whose is it
- GNM's FEMALE CLASS MEAN neck is thick: 365 mm at its narrowest (ring 19), 407 at ring 13; ANSUR women 330 / 371
  (base). Male class mean 385 / 423 (ANSUR 398 / 435). So GNM's prior is +11 % on women, -3 % on men.
- Tess's SOLVED identity made it THINNER: 334 at the narrowest (= ANSUR's mean woman), 374 at ring 13. The change
  from her class mean (-33 mm linear) is head_000 +0.91 sd (-29.7 mm) and head_001 -1.24 sd (-12.9 mm), then
  head_003 / 024 / 009 / 004 (+1.5 .. +2.3 each). Garrett: 361 against his class mean's 385: head_001 -1.97 sd
  (-20.5 mm), head_000 +0.22 (-7.2), head_004 +1.54 (+5.7).
- So the neck IS moved with no read, by the two largest components (head_000: -32.7 mm of neck girth per sd, also
  the head's size / width; head_001: +10.4): the neck's girth has an sd of 35.9 mm over GNM's identity prior and no
  picture read holds it. FOR THE SOLVE (not touched): a read or a prior on neck girth (ring 19 loop length; the
  linear row is in spikes/headbody/p7_gnmneck.py `dgirth`), e.g. held to the body's own neck or to 0.203 x stature
  (women) / 0.227 (men) +- 6 %.
- 374 "on a slim woman": that is ring 13 = the neck's BASE (ANSUR 371). Her narrowest is 334. The thin one is the
  MakeHuman body at weight 0.15: 290 at the narrowest, 2 sd under ANSUR's women.
- PROPOSED ATTACH RULE: never inflate the body to an unread neck blindly. Report head girth / body girth at the
  narrowest ring; within +- 8 % the body follows the head's neck base; beyond it, the report names it as a conflict
  to settle (body weight / muscle, or a neck-girth step in the solve), and the bib-following blend below still
  joins them smoothly over the shoulder slope.

### Chest holes in Tess's neck-bent tiles (item 4): a REGRESSION ON MAIN, fixed here
- Not clothing, not normals. `faceshapes.displacements` (gnmnative, 75a6a10: GNM's own mouth) gave vertices away
  from the face the jaw's rigid move x 1.0 instead of x the jaw weight; meant for GNM's teeth and tongue, it also ran
  on the SKIN: every body vertex under the neck got jawOpen's 25.9 mm (old-path export ng_G00.glb: all 2,871 vertices
  from 35 to 85 cm under the top move 25.9 mm in jawOpen, 9.9 in jawOpen_mouthClose, 8.9 in tongueOut). The export's
  `rigid_near` then weights "whatever a face shape moves" 1.0 to Head: in all three GLBs read (hb_tess, hb_garrett,
  ng_G00) the trunk within 16 cm of the centre line is Head 1.00 down to the hips. Head turn / neck bend carries
  the chest with the head: Tess's bare chest skin swung 138 mm (mean) away and left holes; Garrett's is out of frame.
  The log line "rig: body: 12239 vertices the face shapes move 3 mm or more are Head 1.00+ (9213 weren't)" was
  saying it. The look-path skin (rig() on the built mesh) is right (Spine2 0.6-0.9 on the chest): only exports with
  face shapes on a GNM-mouth head are hit.
- This also made much of the "crumple" at the neck's base in hb_02 (the band between Head-1.0 chest and the neck).
- FIX (faceshapes.py, 2 lines): the rigid share x 1.0 only for kind teeth / tongue; on a one-mesh skin by index,
  vertices that are not GNM's (under the seam ring) get no face-shape move at all. tests/test_face_shapes.py passes.
  Exports made since gnmnative's merge should be redone. The posed check will be re-run after the placement fix.

### References (workspace/neck_refs/, README with sources and licences)
Wikimedia Commons: Female_neck.jpg (woman, 3/4 front), Young_woman_s_neck.jpg (side, head turned),
Sunburnt_neck_and_shoulders.jpg (back), Adam_s_apple_35.jpg (young man, side / 3/4), a shirtless bald man 3/4,
Cou.jpg (old man, back), Gray's 1194 / 1195 / 385 (surface forms, SCM, trapezius), a 1913 landmarks plate. GAP: no
same-subject neutral front / side / back set, no bare male front / back; Commons rate-limited the search. Joe or a
later pass should add a proper turnaround.

### Proposed fix (waiting for the coordinator)
1. SEAT THE HEAD BY ITS OWN NECK BASE: GNM's evaluation includes the bib (rings 0-12: pit of the throat, clavicle
   line, trapezius slope). Place the head so the bib lies on the body's shoulders: a least-squares translation
   (up / forward) of GNM's bib onto MakeHuman's surface round the neck's base, instead of skull-on-skull. Expected:
   chin over the pit 73 (Tess) / 84 (Garrett), top over the pit ~288 / ~305 (ANSUR 299 +- 14 / 318 +- 14), the
   stature made up by trunk + legs as now.
2. THE BODY FOLLOWS THE BIB, NO PULL-DOWN: replace the displacement field by project-and-relax. Target surface =
   GNM's bib near the ring fading into MakeHuman's own surface over the whole shoulder slope (weight 1 at ring 13 ->
   0 by about ring 3, ~11 cm out); the bridge's rows and MakeHuman's top loops are laid ON that surface and evened
   out along it. The neck, pit and trapezius next to the head are then GNM's own forms (consistent with the head),
   the shoulders MakeHuman's; nothing above the ring changes.
3. Lowering the ring itself (asset rebuild at ring ~9) is NOT needed for this and stays optional.
4. POSE: after the faceshapes fix, re-measure the Head weight on the ring; then smooth it down the neck by height
   (Neck / Head sharing) in rig.py's rule for the native head, with a test.

### After the faceshapes fix: the posed neck (2026-10-12; still at the gate, no rig.py change)
- The fix is its own commit 855e77f (faceshapes.py + test_jaw_leaves_the_body_under_the_neck, which fails on main
  with the trunk moved 23.0 mm). 2acf86c only takes the earlier mixed-in copy out.
- hb_tess / hb_garrett re-exported (the pre-fix exports kept as /mnt/data/hifipushie/headbody/export_*_before).
  Export log: "body: 3172 vertices the face shapes move 3 mm or more are Head 1.00+ (146 weren't: least 0.90)"
  (was 12239 / 9213 weren't / least 0.00).
- Sheet workspace/human_renders/hb_04_pose_after_weights_fix.png (spikes/headbody/sheet04.py): REFERENCE | NOW
  raking | NOW shaded | BEFORE raking, head turned 45 and neck bent 35. BLUNT: nearly ALL of the crumple was the
  regression. Now: no holes, no jagged bridge, no torn chest on either model in either pose; the neck's base turns
  and bends as one smooth surface. What is left is the REST shape posed: a long stovepipe neck on a shelf (the gate's
  subject), and on the neck-bent back views a soft dent where the nape meets the shoulders. It still does not read
  as the references' necks (no trapezius rising to the skull, no SCM), but nothing is broken by the pose.
- Head weight down the neck, read from the GLBs (vertices within 11 cm of the Neck joint's axis, 2 cm bands, mm
  above the Neck joint; mean [min-max]):
  | band | Garrett NOW | Garrett BEFORE | Tess NOW | Tess BEFORE |
  |---|---|---|---|---|
  | +45 | 0.99 [0.95-1.00] | same | 0.95 [0.82-1.00] | same |
  | +25 | 0.95 [0.77-1.00] | same | 0.82 [0.57-1.00] | same |
  | +5 | 0.79 [0.51-1.00] | same | 0.64 [0.36-0.86] | 0.69 [0.36-0.97] |
  | -15 | 0.51 [0.22-0.97] | 0.61 [0.23-1.00] | 0.55 [0.49-0.61] | 0.82 [0.58-0.97] |
  | -35 | 0.38 [0.03-0.60] | 0.77 [0.13-1.00] | | |
  | -55 | 0.14 [0.00-0.31] | 0.93 | 0.00 | 0.00 (her chest is under the top) |
  | -75 and below | 0.00 - 0.01 | 1.00 | | |
  So the falloff is now monotone from the skull's base to 0 at ~7 cm under the Neck joint; Neck carries 0.16-0.33
  and Spine2 takes over below. The spread inside a band (0.22-0.97 at -15 on Garrett) is front against nape: the
  rule's floor climbs to the skull's base at the back by design. Whether that needs smoothing is for after the
  placement fix: judged on the tiles, it does not crumple.
- Reference gap (no more Commons requests): missing = a same-subject neutral front / side / back turnaround of a bare
  neck and shoulders (a woman, a man), a bare male front and back, and the same subjects with the head turned ~45
  and looking up.

## Round 3 (2026-10-12): the neck fix as built

### The rule (onemesh.py; general, no constant of any character)
1. SIZE: `base.head.size` default = (stature / the sex's mean stature) ^ alpha, alpha 0.29 women / 0.24 men (ANSUR
   II: head measures go as stature ^ 0.07 .. 0.36; tragion - top of head 0.29 / 0.24): 1.000 at 1.627 / 1.755 m,
   Tess 1.002, Garrett 1.002, a 1.95 m man 1.025, a 1.50 m woman 0.976. A number fixes it.
2. SEAT (`_seat`): start skull on skull, then translate the head up / down and forward / back until GNM's own BIB
   (rings 0-9 of its skin: shoulder slope, clavicle line, upper back; `_bib`) lies on the MakeHuman body's surface:
   point-to-plane least squares, pairs within 4 cm, the centre line kept. The stature solve then sets the body's height
   so the top of the head is the stated stature (3 rounds).
3. BODY FOLLOWS THE BIB (`_neck_follow`): the body's vertices within 17 cm (x stature / 1.7) of the ring over the
   surface are, 80 rounds, evened out along the surface and put back on a target surface = the nearest point of
   GNM's bib x w + the nearest point of the body's own rest surface x (1 - w); w = 1 from ring 10 up, 0 from ring 1
   down (smoothstep on the bib's ring coordinate). Nothing is displaced through space. The old `_neck_field` only
   gives the start. Head vertices: untouched (test: still exact to 1e-9 m).
4. A lift of the seat for tall bodies was tried and removed: it does nothing (the body's neck base is laid on the
   bib wherever the bib stands). GNM's neck has its own length x size.
5. Build keys: `onemesh.build_version` (NATIVE_VERSION 2) for native models only; other one-mesh models keep theirs.

### Numbers (mm; ANSUR = for the model's sex and stature, from the allometric fits)
| | chin over the pit | top of head over the pit | head height | neck girth head / body's own | heads tall |
|---|---|---|---|---|---|
| Tess old attach | 74 | 257 | 182 | 290 / 292 | 9.0 |
| Tess previous native | 85 | 300 | 216 | 334 / 288 | 7.6 |
| Tess NOW | 74 | 289 | 216 | 334 / 288 | 7.6 |
| ANSUR, woman 1.636 m | 81 +- 15 | 300 +- 11 | 218 +- 10 (memory) | 330 +- 18 | |
| Garrett old attach | 90 | 318 | 229 | 368 / 365 | 7.8 |
| Garrett previous native | 102 | 323 | 220 | 361 / 359 | 8.0 |
| Garrett NOW | 91 | 312 | 221 | 362 / 359 | 8.0 |
| ANSUR, man 1.772 m | 87 +- 16 | 319 +- 12 | 233 +- 11 (memory) | 398 +- 25 | |
Body moved by the follow: Tess up to 41 mm (her shoulder slope rises to the bib), Garrett 36 mm; no folded quad.

### Per-tile verdict (hb_05; reference first, blunt)
- TESS rest front: reads as a neck. Short, tapering, the trapezius rising to under the ear as on the reference.
  Against the reference woman it is THICK at the base and blank: no clavicles, no SCM, no throat pit.
- TESS rest side: reads as a neck: forward lean right, nape runs into the upper back. A slight hump remains on top of
  the shoulder behind the neck.
- TESS rest back: slope and width fine. The vertical ripples between the shoulder blades are still there (they are in
  the old attach too: MakeHuman's coarse upper back, not the attach).
- TESS three-quarter: fine. TURNED: clean, no crumple. LOOKING UP: clean but a featureless tube under the jaw (the
  reference shows the SCMs and the pit).
- GARRETT rest front / side / back / three-quarter: all read as a man's neck; side is the best tile on the sheet
  (the previous column-on-a-shelf is gone). TURNED / LOOKING UP: clean.
- Both: what separates them from the photographs now is surface anatomy, not placement or length.
- hb_06 (full figures): head-on-shoulders proportion reads right for both; Garrett's head a little small (GNM's male
  mean, 8.0 heads), as before.

### Tess's thin-necked body (the conflict rule, as built)
- MakeHuman's FEMALE neck is ~295 mm at ANY weight or muscle (292-299 from weight 0.15 to 0.6, muscle 0.4-0.65):
  more body weight does NOT settle it, so I did not make a heavier Tess. Her head's neck (334) is ANSUR's mean; the
  body's own (288) is 2.3 sd under.
- RULE: the neck from the ring up is the HEAD's; the body's neck base is always laid on it. `attach_report` flags
  NECK CONFLICT past 8 % with each side's distance from ANSUR for the stature and which side is the unusual one, so
  the caller changes that side. Never a silent inflate or thinning.

### The body range (hb_07; spikes/headbody/mkrange.py, models hb_r_*; class-mean heads)
| body | stature | heads tall | chin over pit | neck head / body | flags |
|---|---|---|---|---|---|
| woman 30 | 1.59 | 7.5 | 64 | 363 / 290 | NECK CONFLICT (+25 %; head +2.1 sd, body -2.0 sd) |
| man 30 | 1.73 | 7.9 | 69 | 384 / 358 | none |
| heavy man (weight 0.9) | 1.72 | 7.9 | 69 | 384 / 356 | none |
| very slim woman (0.05) | 1.59 | 7.5 | 65 | 363 / 292 | NECK CONFLICT |
| muscular man (0.95) | 1.73 | 7.9 | 71 | 384 / 357 | none |
| tall man 1.95 | 1.95 | 8.7 | 75 | 395 / 408 | top of head over the pit 300 (341 +- 13): head + neck short for the stature |
| short woman 1.50 | 1.50 | 7.2 | 62 | 357 / 273 | NECK CONFLICT (+31 %) |
| old man 75 | 1.71 | 7.8 | 70 | 383 / 355 | none |
| teen girl 14 | 1.56 | 7.4 | 64 | 360 / 285 | NECK CONFLICT; adult ranges |
| child 8 | 1.25 | 6.2 | 57 | 355 / 296 | NECK CONFLICT; adult ranges |
- Every body builds, stature exact, no folded quad, ring matched, the neck reads as a neck in the tiles.
- WHERE IT FAILS, and why: (1) WOMEN with a class-mean head: GNM's female class-mean neck (363) on MakeHuman's female
  neck (290): a bull neck. It is the head model's prior (+11 % over ANSUR), flagged; the fix is a neck prior / read
  in the solve, not the attach. (2) VERY TALL: an average head + neck on a 1.95 m body (8.7 heads; flagged):
  GNM has no stature link. (3) CHILD / TEEN: GNM is an adult head model: an adult face at 0.92 size on a child's body;
  proportion 6.2 heads happens to be near a child's, the face is not a child's. Not covered.
  (4) Class-mean necks sit ~0.8 sd short in front (chin 64-71 mm over the pit, ANSUR ~77-83 by memory-based head
  heights): GNM's own necks are short (template 71).

### Tests
tests/test_headbody.py (6): exact head (now x the head's own size), lip_close inside GNM's basis, stature, ring +
no folded quad, `test_any_body_takes_the_head` (8 adult bodies: stature, exact head, ring, no folded quad, every
report check in range; the tall body is allowed exactly its one flag), old path hash unchanged.
