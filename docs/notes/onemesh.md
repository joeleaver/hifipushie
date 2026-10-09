# hifipushie notes: onemesh

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

## One human mesh (2026-10-06, "onemesh" agent, branch worktree-agent-aac6bb85823bc8809; renders `workspace/human_renders/om_*`)

The user: "we seem to always be fighting the makehuman/GAN mesh combination ... So we had one mesh?", then a stretch
goal (the same topology driving stylised humans: feature animation, cartoon, low-poly, anime, by macro sliders fitted
to references), then two requirements on the interface: sliders are what a SOLVER sets ("sliders are always
ambiguous"), and guard rails against "blind measurements while completely ignoring the integrity of the rest of the
model".

- Research (Phase 0): nothing open replaces GNM + MakeHuman. Anny (NAVER, Apache-2.0 code, MakeHuman's CC0 assets,
  WHO-calibrated ages) IS MakeHuman's mesh + macros, i.e. what makehuman.py + anthro.py already are, with MakeHuman's
  faces; MHR (Meta, Apache-2.0, scan-based, 7 LODs, 72 FACS shapes) has no eyes / teeth / mouth, PCA identity and no
  children; SMPL-X / STAR / SUPR / FLAME non-commercial; MetaHuman Epic-only; GNM still head only (a body is on its
  roadmap: the body half here stays swappable). MPFB's `faceunits01` (CC0, 52 ARKit shapes on MakeHuman's head) is a
  reference for our face shapes. Decision (with the user): fuse GNM's head topology onto MakeHuman's body, once.
- The asset: `src/hifipushie/human_mesh.npz` (2.1 MB, in the package), built by `spikes/onemesh/make_asset.py`
  (deterministic, prints the arrays' sha256; `register.py` = make_field's registration returning the correspondence;
  `sheet.py` = the hand-check sheets; `wire.py` / `meshview.py` = a PIL clay / wire viewer, no Blender).
  MakeHuman's body below a neck loop C (42 vertices; one loop above `base._neck_loops`' top one: that one lies on the
  trapezius), GNM's skin above its neck ring 13 (110 vertices) + sock + eyes + teeth + tongue, three bridge rows
  110 -> 82 -> 58 -> 42. Row units: plain quads and 3-edges-onto-1 reductions through two new vertices, spread evenly,
  palindromic from the front centre (mirror symmetry), phases searched for 3-5 edges per vertex. Dead ends, in order:
  two rows 110 -> 56 -> 42 (6-edge and 2-edge vertices); 4-edges-onto-2 units round ONE vertex (the middle fine vertex
  is a 180 degree corner of a quad: 36 "folded" quads); Laplacian relaxation (rows collapsed unevenly); placing the new
  loops by the turn about a vertical axis, by arc length, by arc length pinned at the sides (each sheared or folded
  where C climbs the neck's side: the rows join vertices BY INDEX, so the parameter must be the index). Now: no folded
  quad, bridge aspect median 2.3 / p90 3.2 / worst ~4 (A and C are not parallel: the gap is 1 cm at the sides, 3 cm
  front and back; an artist would tilt the cut). `edits.json` beside the script = hand corrections (moved vertices,
  spun edges; `--obj` / `--edits-from` round trip through Blender), not yet used with a real edit.
- The design that made it simple: every GNM skin vertex and bridge vertex is BOUND to a point of MakeHuman's
  reference surface (triangle + barycentric; registration residual 0.17 mm rms). `onemesh.bound(params)`: any
  MakeHuman body (growth, sex, weight, bust: whatever makehuman.body takes) carries the head = a similarity (the
  head's size) + the remainder smoothed over GNM's mesh, held hard round the stitch; eyes / teeth / tongue rigid with
  a scale from the skin beside them. Ring A lies within 0.2 mm of the body at every age; the bound head within 0.2 mm
  mean / 0.5 mm p95 of the body's own head (follow_body: 2.5 / 6-9 mm). No per-age delta arrays, no head scale.
- `base.gnm_head` runs unchanged and one hook (`head["bound"]` -> `onemesh.hook`) lays everything it made, as a
  DIFFERENCE from GNM's template (identity, expression, regions, pose, eye size, planes; then pushes / simplify in
  world), on the bound head, faded to 0 over 7 rings above the stitch. So landmarks, eye seating, lip zip, GnmFace's
  carry keep working. `onemesh.head_desc`: the seed stripped of its own age / sex / weight and `features` solved by
  headfit.follow on a pseudo base; `dimorphism` (0.8) from head_fields on the head only; `toward`.
- Wiring (4 guarded branches in base.py; old paths bit-identical, checked by hashing the built base of the golfer, two
  grafted humans and the template against main's code): `base.source` -> `onemesh.template` (fused quads at this
  body's shape: "fid" = asset index, "n_mh", "n_body", "chin_lm", "chin_mh"), `base.head_of` -> `onemesh.head`
  (posed by the same skeleton warp as the body), `base.surface`: one quad mesh -> Catmull-Clark -> IMLS, no tube /
  cross-fade / seam weights, "graft" None, "src" = arange. `rig_template._one_mesh`: the asset's weights by index
  (MakeHuman's hand-made ones; through the binding on the head; 139 bones folded as before), the arm's side handed to
  Neck within GRAFT_REACH above the stitch; rig3's head rule runs on top as for any base with lm_* joints.
  `humans.spec(source="human")` / `human(..., source="human")`.
- `humanfit.py` + tools `measure_human`, `fit_human`, `nudge_human`, `human_reference`, `guide(topic="human")`:
  named measures (body cm via anthro.measure; face mm from the 68 landmarks + eye centres, `FACE`; ratios "a/b");
  `solve` = minimal-change Gauss-Newton (landmarks are LINEAR in GNM's identity components: headfit's LB tables, so
  the Jacobian is analytic; body macros by finite differences), every measure not asked for held, far landmarks
  held, ridge toward the current state, components clipped at 2.6 sigma, and the step CUT BACK where an unasked face
  measure would move > 2x its tolerance (`COLLATERAL`); `nudge` (one landmark, mirror together, the rest a Gaussian
  push in shape.push_more, reported as "the sliders can't do this"); `fit_views` (cameras + identity jointly on named
  2D points, multi-view); `side_effects` (all measures before -> after, UNINTENDED, displacement outside the asked
  region); `integrity` (faces folded BY THE EDIT, edge stretch per region against the same body with a plain head,
  lids over eyeballs, lips crossed, sigma). A broken result is not saved unless forced. Lessons: comparing folds
  against the plain head called every open lid broken (compare against the state before the edit); a zipped mouth's
  topology depends on the shape (integrity unzips both); a centre landmark a hair off x = 0 got its push twice (the
  mirror rule): pinned with an offset; one tiny lip face turns with any change (limit 6 faces).
  Measured: nose_width +4 mm met with 2.6% of the mesh moved > 1 mm away from it; "eye_width x3" comes back at
  +3.5 mm, held at 31% of the step; a synthetic two-view fit of another seed: 0.3 px, 3D landmarks 3.3 -> < 1.5 mm.
- Tests: `tests/test_onemesh.py` (asset topology / symmetry / bridge, the stitch at 1-78 y, determinism, identity
  fades at the stitch, old paths never call onemesh, measures vs the grafted path, weights by index),
  `tests/test_humanfit.py` (measures, a met measure, adversarial requests, nudge, fit-back from images).
- Later the same day: GNM's lower neck rings (13..21) are SLID along their own columns on MakeHuman's surface so ring A
  ends 21 mm above C all round (it was 1 cm at the sides, 3 cm front and back); the rows are still skewed at the
  neck's side (A's and C's vertices are spaced differently round the neck, and rows join by index): bridge aspect
  median 2.3 / p90 3.3 / worst ~5, no folded quad, no gap (the pale slivers in om_02_neck's three-quarter back view
  were the PIL viewer culling warped quads at the silhouette: with back faces drawn the surface is closed; min quad
  area 6 mm2). An artist's hand pass through edits.json is still the fix, and edits.json is still unexercised.
  Image fits and solves hold the skull (`_skull_basis`: headfit's cranium and far dense points; it moved 16 mm
  unseen before). Fit replies carry the whole DRESSED figure before | after (`_human_figure`, two looks, ~1-3 min).
- Style, round 0 (`humanstyle.py`, `base.style.human`, `human(style=)`, sheets `styles/human_feature|cartoon|anime|
  lowpoly.json`; scratch sheets only, adult clay): head sliders are ops on GNM's vertices inside `onemesh.hook`
  (head_size about the neck's top, cranium, eye_spacing / eye_height as Gaussian moves of the orbits, nose toward the
  face, jaw / chin as a narrowing of the lower face, cheeks along normals, mouth, exaggerate = the identity x a
  factor), faded at the stitch; body sliders (legs, arms, torso, shoulders, hips, hands, feet, limbs, waist, chest)
  are joint targets + girths through `retopo._skeleton_warp` inside `onemesh.template` (the head rides: `head_rest`,
  `_carried`), so rig, weights, landmarks and face shapes stay. RANGES clamp each slider. What round 0 showed: a
  short ramp for `cranium` made a ledge at the brows (now from the eye line up over 2 interoculars); jaw + chin at
  full strength made the chin a line (capped at 62%); `face_flat` toward a plane collapses lids and lips (range cut
  to 0.25: an anime face needs its features on a smooth proxy and its own eye part); girth on the neck -> head bone
  squeezes the HEAD (no `neck` slider); `nose` leaves the nostrils as a dark pit; integrity now reads stretch against
  the head's own scale. The four sheets are FIRST GUESSES: not fitted to any reference, not seen dressed, not judged.
- HANDOVER (onemesh agent, context nearly full, 2026-10-06). Branch worktree-agent-aac6bb85823bc8809; tests
  test_onemesh.py / test_humanfit.py pass at the last asset (sha c040e681...); main merged in at f5e7b3c.
  Scratch (worktree `scratchpad/`, untracked): t3.py (one clothed person through the tool), hf1/hf2/hf3.py (fit
  exercises through the tools), st1.py <png> [labels] (each style slider on an adult, clay, PIL: seconds), neck.py /
  neckb.py / worst.py / flip2.py / chk.py (bridge views and numbers), oldhash.py + `orig/` (old paths bit-identical
  against main's code: re-extract with git archive), lineup log. Line-up panels: /mnt/data/hifipushie/onemesh/lineup;
  re-lay with COMPOSE=1 spikes/onemesh/lineup.py <that dir>.
  Open, in the order I would take it:
  1. Proof still owed: rig sheets on a one-mesh adult (arm raise 60, head turn 33, nod; `rig(name, pose=...)`), one
     export through export_asset (topology = the base's own quads via retopo.base_quads, which already skips
     graft_head for this source) + Khronos + rig audit, a face-shape sheet (GnmFace reads head["carry"]; carry has
     "fade" per GNM vertex and subdivide 0: faceshapes must multiply deltas by fade and not assume one subdivision:
     UNTESTED and likely needs two lines there).
  2. Guard rails not built: functional checks as a pre-export gate (blink, jawOpen, rig pose), self-intersection
     (lips / teeth; only lid landmarks vs the eyeball now), warnings that persist (each tool call re-runs integrity,
     nothing is stored), plausibility for body sliders, outline / mask fits (stylised references are read by
     silhouette), MediaPipe Face Landmarker + a 478 -> 68 table as the default detector (Apache-2.0, ~4 MB;
     Depth Anything V2 SMALL only is Apache; the anime detector is MIT but drags mmdet / mmpose; Marigold's licence
     unverified).
  3. Style rounds against references (the user's stretch goal): fetch CC / permissive sheets into
     workspace/human_refs/, landmarks -> human_reference for the face, outline fits for the body, tune the sheets,
     send reference | ours | sliders. Missing sliders the rounds will want: neck thickness / length in head space,
     an anime eye PART (bowl + iris disc, option of the same mesh), face projection onto a proxy, feature simplify
     per region, per-style custom normals and the toon look / outline recipe in the export, low-poly as un-subdivided
     levels with flat shading. A 1.45x eye already stretches lid edges ~2.3x against the head's scale (integrity
     warns from 1.8x): a 3x anime eye will need the alternative eye part.
  4. Template: the neck's side rows by hand (edits.json) or a hand-drawn GNM loop; thin GNM's neck for LOD1+; UV
     repack; eyes / teeth / tongue / sock of the asset are unused by the field (blobs + the kit interior as before).
  5. `like`, `neck`, follow_body's strength are ignored on this source; humanfit's body solves take minutes (finite
     differences on MakeHuman builds); head_sheet is flat-shaded.
- Proof + Garrett, round 1 (2026-10-07/08, "onemesh2" agent, branch `worktree-agent-abebc7b0353b5a6fe`; renders
  `workspace/human_renders/om2_*`, line-up re-rendered `om_10_lineup_*`; scratch DURABLE in /mnt/data/hifipushie/onemesh2/:
  run.sh <script> (worktree code on the main workspace), run_orig.sh + orig/ + oldhash.py (old paths bit-identical vs
  main 23b8b9e), exp.py (export), sheets.py (rig poses through rig(glb=); "-" = look build), closes.py (rest / jawOpen /
  blink / smile close-ups of a GLB), glbz.py + zview.py (z-buffered numpy views of a GLB's or a mesh's triangles, back
  faces red: what showed the mouth's faults when Blender's clay hid them), idx1.py (face shapes by index on retopo.wrap's
  quads without an export: unevenness, contact-ring gap, mouth crops; env RAW / NOMEET / NOSOCK / CC / LC), blinkglb.py
  (lid jag + unevenness from a GLB's own targets), torn.py (where a quality report's folds / turned faces are, by GNM
  group), facem.py (humanfit's face measures for ANY base, old path too), g_try.py / g_fit.py / dense_fit.py (Garrett's
  fits), proof.py + seatlib.py (regen's: s0urc3's seated pose, two GLBs, same cameras), bodym.py, mk_garrett.py,
  variant.py / setbase.py / setkey.py (spec patches), tests.sh).
  - Fixed: `humanstyle` head_size pivoted on a bounding-box corner (the fade's 0.4-0.6 band is empty: levels 0.39 / 0.61):
    the face slid 10 mm sideways and 2 cm forward. `onemesh.VERSION` is in store's build key and base.surface's key
    (bump it for one-mesh field changes; old paths keep their keys).
  - Phase 1 read: rig on a one-mesh adult is MakeHuman's own (head turn, arm, knee clean; nod: the known nape bump;
    audit 8 BAD of 51). Decimated export works (Khronos 0/0) but its blink is ragged (no face focus on the test adult).
  - Own quads (parts.body.topology "wrap") is now THE path for face shapes on the one mesh: `retopo.base_quads` returns
    `gnm` (each vertex's GNM id, into topology_<p>.npz), does not snap GNM's interior surfaces (non-exterior skin) or
    ears onto the field (they folded: TORN at both eyes, 60 spots on Garrett's ears), and adds GNM's mouth sock
    (`_with_mouth_sock`: placed as the skin, carried by the skin's post-placement moves, tucked in by SOCK_TUCK so it
    can't stand out through the lips' corners). asset attaches `gnm_index` to the low poly when its vertices are still
    the topology's; `faceshapes.apply` then passes it: GnmFace takes GNM's offsets BY INDEX (`_by_index`), no lid seal,
    the neutral closes the lips on GNM's contact ring (`_lip_rings`, `_lips_meet`, smooth in x; taken back by a shape in
    proportion to how far it parts the lips) and at the corners (`_corners_meet`, kept). The kit's slit isn't meshed on
    this path (`voxels`); give `interior.slit` ~0.0003 so the field has no gash for the bake. mouth_gap may be left out
    on the one mesh. `asset.mesh_quality(designed=)` leaves the lid margins, lips, interior and sock out of TORN; GNM
    head faces are never dropped as hidden. Adult: jawOpen unevenness 0.05 (projection on the same mesh: 3.19), blink
    0.03 (v23 0.15). Test `test_face_shapes_by_index_on_own_quads`.
  - Garrett: `workspace/om_garrett` (garrett_v20 copy, clothes out; `om2_g23` = the same on the old path). head_size
    1.12 (v23's head scale: interocular 69.5 mm), fit_human to v23's 17 measures, then dense_fit.py (both are GNM rows:
    identity by ridge LS on every exterior skin vertex, face weight 1 / cranium 0.3 / ears 0, then an RBF warp in
    GNM's frame, base.head.warp): face 3.21 -> 0.55 mm mean, 1.09 p95; head 2.85 / 10.6 (cranium under hair). Then own
    quads + mouth_gap 0.003 + interior.slit 0.0003, skin.only eyes. Export /mnt/data/hifipushie/onemesh2/exp_garrett3
    (40k, Khronos 0/0, no TORN, shapes <= 0.13, seated clean, audit 7 BAD vs v23's 9). Stature +2.9 cm (head grows
    from the neck's top): body.height 1.771 would give it back (not done).
  - Round 2 (same agent): the bridge is five rows (COUNTS 110-94-78-66-54-42, SHEAR 0.85: median aspect 2.36 ->
    1.71, worst corner cos 0.18 -> 0.31; the toddler's ring of pits at ring A gone; wider IMLS kernels there made it
    WORSE: speckle, reverted). Asset rebuilt: every one-mesh model's topology changed. Garrett v15: body.height 1.7715
    + head_size 1.138 (stature 180.6, interocular 69.8), dense fit again (cranium weight 1, lips 0.3: face 0.68 /
    1.30 mm, head 1.45 / 7.7); export exp_garrett5 (Khronos 0/0, no TORN, height range +-7.6: interior texels keep the
    low poly's surface in the bake). Lip corners: the sock tucked in behind the corners (SOCK_TUCK), inner rolls pushed
    by the outer skin's normal. Hair: `hair._measure` (one mesh only) skips pockets in the head (POCKET: GNM's ear canal
    rooted his nape locks 4 cm in). A groom regrow on Garrett grows tiers over / buries his hand locks: don't; the
    band of bare volume at his front hairline needs a "re-seat hand locks on a changed scalp" step (hair thread).
  - Reference pass 1 (concept_v8 front crop + concept_v6 desk painting at -45): detect.py (MediaPipe Face Landmarker
    from /mnt/data/hifipushie/facerefs_venv, MP68 table) -> hrefs.py (human_reference, drop lists) -> refsheet.py
    (reference | models through the fitted cameras | blend | landmarks). Copy `om2_gref` (om_garrett untouched):
    front 6.8 -> 3.3 mm, desk 7.3 -> 3.9 mm reprojection; sheet human_renders/om2_r1_pass1.png. Couldn't: jaw
    contour (MediaPipe's != GNM's: +21 mm jaw, dropped), iris vs eyeball centre in 3/4 (dropped), hooded lids (lids x3.2
    BROKEN: dropped), neck_circ measured at the chin's height reads -9 cm when the chin moves (measure bug), no ear /
    hairline / crown evidence. Next: an outline fit (silhouette chamfer through the fitted cameras), pass 2.
  - Reference pass 2 (2026-10-08; scratch pass3.py om_garrett om2_gref3 1, sheet human_renders/om2_r2_pass2.png =
    reference | before | pass 2 | blend | landmarks, model `om2_gref3`; om_garrett untouched apart from its
    human_refs.json, which holds the cameras the sheet uses). Order: points (identity; eye centres, lid corners, lower
    lids back in; no jaw, no upper lids) -> `fit_hood` (upper lids) -> `fit_outline` (front view only, 5 rounds).
    - `humanfit.fit_outline`: the head's silhouette through the fitted camera (vertices whose faces turn front to
      back, `_silhouette`), each outline point's miss along its normal turned into a move in the image plane at that
      vertex's depth (capped `OUTLINE_STEP` 4 mm a round), then into GNM's frame and solved as an RBF warp appended to
      base.head.warp; brows / eyes / nose / lips landmarks and skin far from the targets held (`OUTLINE_HOLD`).
      Mirrored targets by default (`symmetric`): one view's outline warped only its own jaw (a lump). Putting the
      outline into fit_views' identity solve folded lids and lips: dropped. Front: silhouette miss 8.3 -> 0.8 mm,
      widths at eight levels (temple .. chin, MediaPipe oval pairs over the photo's pupil distance) within 1-2.5% of
      the photo. The DESK painting's outline is not used: its camera is the weak fit and with it the jaw came out 8%
      wide on both sides.
    - `base.head.shape.hood` (m | {amount, forward, reach}; `base._hood`): the fold between upper lid and brow comes
      down (and 0.4 of that forward), the lid margin with it by the falloff, gated off at the corners' height (lower
      lid and eyeball seat stay), landmarks ride. 3 mm: upper lid landmarks -1.2 mm, eye height 8.9 -> 7.7, 0 folds,
      lid stretch slightly LOWER. `humanfit.fit_hood`: one number, linear, [0, HOOD_MAX 5 mm], halved until integrity
      holds. Garrett asks 4.0 mm (upper-lid rms 1.28 -> 0.93 px).
    - neck_circ: one level (`NECK_AT` 0.35 of neck joint -> body chin) on body + bridge vertices only
      (`humanfit._neck_girth`; anthro.measure unchanged): 31.9 cm before and after any face fit.
    - Left: the points step with lid corners + lower lids reads lids x3.2 BROKEN by itself (x2.7 warning after the
      hood); the model's pupils are 8% closer than the photo's at matching face width (69 mm already: widening
      them fights plausibility; the photo's eye centres or MediaPipe's oval are suspect); a bald clay head under the
      hair's silhouette (no crown / hairline evidence); asymmetric pictures are made symmetric by design.
    Tests: test_humanfit test_neck_girth_ignores_the_face, test_hooded_lids_fitted_from_a_picture,
    test_outline_fit_is_symmetric_and_holds_features.
  - Reference pass 3 (2026-10-08; the coordinator on pass 2: "matches by measure but bloated and jowly, pear-shaped";
    scratch pass4.py om_garrett om2_gref4 <hollow mm> 1, sheet human_renders/om2_r3_pass3.png = per view a clay row
    (reference | before | pass 2 | pass 3 | blend | landmarks) and a LIT row (key from the upper left, smooth normals:
    refsheet3.py), model `om2_gref4`; NOT applied to om_garrett).
    - Measure first: `humanfit.cheek_hollow` = horizontal sections from the nose's base to the mouth's corners, the
      OUTER cheek's contour (from 0.4 of the way nose wing -> jaw contour, `HOLLOW_FROM`: nearer the nose the deepest
      point is the nasolabial fold, 3-4 mm on every head) against its convex hull. before 0.3, pass 2 0.35, pass 3
      2.2 / 2.6 mm. (A vertical section at fixed x read the muzzle's side, and a section through the jaw's underside
      read every face as a 12 mm bulge: both dropped.) The points step (identity) is what made the cheeks full: on a
      vertical profile -3 -> -8 mm, the outline only -8 -> -10.7.
    - `fit_outline(structure=True)` (default): outline targets on GNM's cheek regions count `STRUCTURE_SOFT` 0.25 and
      the cheeks' front (cheek regions, normal forward) is HELD (`STRUCTURE_HOLD`), so the warp widens the head's sides
      (zygoma, jaw angles) instead of filling cheeks; ear vertices are left out of the silhouette (`skip_ears`). Per
      view `outline_axis: "y"` (heights only: the desk painting's near-side jaw / cheekbone heights, weight 0.7; its
      miss 9.9 -> 4.2 mm) and `outline_weight`. Widths still within 2.5% of the photo at all eight levels.
    - `base.head.shape.hollow` (m | {amount, radius, at, share}): a dent under the cheekbone, centred where a ray from
      the jaw/mouth landmarks' mean, 37 deg out from straight ahead, meets the cheek (the mean of two landmarks across
      a convex cheek is INSIDE it: the first try dented half its amount at the face's side; the frontmost point dented
      the lips' corner). 5 mm on a plain head: hollow 0 -> ~2 mm both sides, no folds. Pass 3 used 2.5 mm.
    - MediaPipe's oval on the front photo (overlay oval_front.png in scratch): runs on the face's edge from the ear's
      root down; its top (temples, 127 / 356, and the forehead) is the hairline: those points are left out now.
    - Honest read of om2_r3: in the lit rows pass 3 has shading under the cheekbones on both views and reads closer
      to the photo than pass 2; but the lower face is still broad and soft, the jaw corners rounded (no bony angle),
      a lump at the subject's left jaw in the front view, and the bald clay head reads small against the hair's
      outline. Next: a jaw-angle control (bony corner + the under-jaw tucked), the points step held off the cheeks.
  - Reference pass 4 (2026-10-08; scratch pass5.py om_garrett om2_gref5 2.5 4 1, sheet human_renders/om2_r4_pass4.png:
    per view clay | lit | lit WITH the groom's volume (hair.cap_mesh mass=True on each model's own scalp: a stand-in
    for the locks), columns before | pass 3 | pass 4; model `om2_gref5`; NOT applied to om_garrett).
    - `fit_views(hold_cheeks=True)` (default): the cheeks' fronts held by `_cheek_basis` (GNM cheek-region vertices
      facing forward, d/d identity), `HOLD_CHEEK` 0.25 / mm. Points step: cheek hollow 0.26 -> 0.23 (pass 3's
      points step: -> full), points rms 3.35 -> 3.63 mm. The outline then widens the jaw more (jaw_width 136.7).
    - `base.head.shape.jaw_angle` (m | {amount, tuck, radius, tuck_radius}): a bump at the jaw's angle, which on the
      bound head lies ~33 mm behind and 20 mm under GNM's lm 3 (GNM's jaw-contour landmarks are on the cheek's side;
      measured: section at lm 3's x, the jaw's underside drops to the neck at y ~ -45 mm), plus the under-jaw (under
      lm 5-6) tucked in, snapped onto the surface in its own x. W-level pushes in gnm_head act on the BOUND head
      (onemesh.hook returns it before placement), so world offsets measured on the final head are valid there.
    - The front view's "left-jaw lump" is not asymmetry: the head is symmetric to 3.6 mm at the jaw (asym.py; same
      before any fit). Straight on (frontal.py) it is both jaw corners standing out past the neck; the fitted
      camera's roll (-7 deg) and pitch (15 deg) show one of them.
    - The "8% pupils" is a definition: MediaPipe's eye points are the irises; ours the eyeballs' centres. The outer
      eye corners are 6% WIDER on the model than the photo (80 vs 75 px). Real miss found: the MOUTH is 15% narrow
      (lm48-54 38.8 vs 45.9 px); the fit took mouth_width 56 -> 52.5 mm.
    - Read: inside the hair stand-in, pass 4 is a pear again: the groom's volume is thin at the temples (it was
      groomed on v23's head) and the jaw now carries the outline's width. The photo's hair outline is clearly wider
      than its jaw. Next: the cranium / temples and the groom's sides against the HAIR outline (not the face oval),
      the mouth's width, then the jaw's width re-judged.
  - Reference pass 5 (2026-10-08; scratch pass6.py om2_gref5 om2_gref6 57 1, sheet human_renders/om2_r5_pass5.png:
    v23 likeness | pass 4 | pass 5, the hair rows with his REAL locks; model `om2_gref6`; NOT applied).
    - `hair.lock_meshes(sc, locks)`: the locks as numpy lens tubes (lock_extents' construction, outer + cupped inner
      face) for quick renders and silhouettes without Blender. His 624 locks are all hand locks in [az, el, h]: they
      re-seat on any head's scalp by themselves (lock_world); no re-seat step was needed (round 1's trouble was the
      scalp rays entering the ear canal, fixed then).
    - The photo's head outline (head + hair against its plain background, scratch hairfit.py) vs the model with his
      locks, levels from the top of the hair to the ears' top: the bare cranium is about right at the temples' skin;
      the HAIR is 15-23 mm per side thinner than the photo's (his groom: volume.sides 6 mm).
    - `hair.lift(spec, sc, {region: m})`: the whole groom fuller by region (lock points' h + groom.volume by the
      volume's own region weights), eased in from the hairline over `LIFT_RAMP` 3 cm (lifted at the line it stood off
      the temples as a shelf). Fitted: sides +22 mm, top -1.4: widths within 3 mm at every level, but the outline sits
      ~11 mm to his left (the photo's sweep is the other way round from the groom's parting side).
    - Mouth: solve mouth_width 62 folded 7 lip faces (BROKEN; `solve` reports, it doesn't refuse: pass6.py saved it
      once, re-run since); 59 squeezes the lip corners past 0.25; 57 is the most that holds (mouthtry.py).
    - Read: with the lift the hair matches the photo's outline and reads as a stiff helmet with flared sides: lock
      shapes made for 6 mm of side volume, pushed out 22 mm. A fuller cut needs regrooming the sides (the hair
      thread's tools), not a lift. The face in pass 4/5 is broader and squarer than v23; v23 keeps the long lean face
      the director approved. Tests tests/test_hair_lift.py.
  - Reference pass 6 = APPLIED (2026-10-08; the coordinator: "v23 is the one that reads as the photo's man"):
    v23 (om_garrett v15) + base.head.shape hood 0.0035, hollow 0.005 (measured hollow 0.27 -> 1.95 / 2.24 mm),
    jaw_angle 0.0025, mouth 56.0 -> 56.5 mm by solve (57 squeezed v23's already-broken lip corners 0.24 -> 0.22:
    refused); no outline warp, no hair lift. om2_gref7 -> om_garrett v16 (scratch pass7.py, applybase.py).
    Cameras for the sheets fitted to v23's own landmarks with no identity (camfit.py; 4.6 / 5.9 mm rms).
    Sheet human_renders/om2_r6_pass6.png (v23 | pass 6, front + desk, clay / lit / his locks). Export
    /mnt/data/hifipushie/onemesh2/exp_garrett6 (30k / 2048, rig + face shapes, Khronos 0 / 0, body quality 16 folded
    edges / 11 turned (v23's export: 13 / 11), unevenness <= 0.13, height range +-6.7 mm); blink vs v23's export
    (om2_r6_blink_v23_vs_pass6.png): same clean closed line, lid jag p95 0.95 / 0.88 (v23 0.91 / 0.85).
  - humanfit's fits (solve, nudge, fit_views, fit_outline, fit_hood) REFUSE a result the edit broke: the input
    comes back with rep["refused"] (`_guarded`), unless force=True. A region already broken in the input (v23's lip
    corners squeezed x0.24 against the plain head) counts only if it got `GUARD_WORSE` 8% worse (`_newly_broken`).
    A 3 cm chin nudge is now refused (test_nudge updated: forced, it still makes its correction layer).
  - Why the photo's face reads wider (2026-10-08; the user's question; scratch widths.py, fovtest.py, contrib.py,
    pass8.py; sheet human_renders/om2_r7_width.png = photo | v23 | pass 6 | pass 7 50% | 100% FORCED, front + desk,
    clay / lit / his locks; v23 copy `om2_v23` = om_garrett v15, cameras fitted to its own landmarks):
    - Half-widths (centre line lm27-lm8 to the face's edge: the photo's MediaPipe oval, the model's visible face
      silhouette, ears left out), photo vs v23: cheekbone level -11 mm (6.6%), nose base -21 mm (12.6%), upper lip
      -20 mm, mouth -23 mm (15%); eyes +4 mm; the brow and the jaw/chin levels are wider on ours (the photo's chin
      tapers to a V, ours is a broad lower jaw: v23's jaw corners sit lower).
    - FOV: the focal is free in the fit and runs to orthographic (5.8 km); pinned at 35 / 50 / 85 / 135 / 200 mm
      equivalent the residual is 4.48 / 3.96 / 3.70 / 3.65 / 3.63 px (free 3.62) and the nose-base deficit 40 / 32
      / 27 / 25 / 23 mm: a wide lens makes the deficit LARGER and fits worse. Not FOV.
    - Ears stand out 18-27 mm past the face's edge in the photo, 0-9 mm on ours; side hair 15-23 mm per side
      thinner (pass 5's numbers); light: with the sheets' key from the upper left our far cheek darkens from 68% /
      80% of its half-width (nose base / mouth), the photo's soft frontal light keeps both sides lit to the edge.
    - Pass 7 option (pass8.py, om2_p7_50): the outline fit on the oval's cheekbone / masseter points only, targets at
      50% of the miss, structure mode + lips held + ears riding the side, a second warp of its own reach (sigma
      0.014; `head.warp` may now be a LIST of warps, base applies each): deficit at nose base 21.9 -> 7.8 mm, mouth
      23 -> 11.4, cheekbone 11 -> 7.1; cheek hollow 2.0 -> 1.3-1.6. 75% and 100% are REFUSED: the face's side
      pushes into the ear's front (tragus edges x0.21-0.24); 100% forced reaches -4 / +4 mm.
    - Integrity: stretch now leaves out edges under `STRETCH_MIN` 0.8 mm on the plain head, or already under it in
      the input (v23's lip corners: a 1.7 mm edge squeezed to 0.55 mm read "lips BROKEN" at any change nearby).
  - Feature controls round (2026-10-08, om_garrett v17-v22; sheets human_renders/om2_r7_*, om2_r8_*, om2_r9_*; the
    user judged feature by feature: jaw "isn't anywhere close", "wrong part of the ear got stretched", "still not
    getting the nose right", then "chunky, handsome, square jaw, cleft chin, cute nose"). Scratch additions in
    /mnt/data/hifipushie/onemesh2/ (run.sh now goes through /mnt/data/hifipushie/bin/capped): jawtrace.json (hand
    trace, likeness_points format; also workspace/om_garrett/likeness_points.json), gridcrop.py / drawtrace.py (place
    and check hand points), jawmeas.py (ramus / gonial angle / gonion vs lobe on trace and on the model's jaw edge =
    first occluding edge on rays from the nose; UNSTABLE on a crisp L: judge by sideview.py), jawsheet.py, sideview.py
    (true profile + from below, numpy), jtry2.sh src dst '<shape json>', earmeas.py (auricle height / width / own edge
    ratios / protrusion top-mid-lobe), earsheet.py, nosebase.py (the nose's base line in the desk view), nosedbg.py,
    evo.py (eyes / mouth part way in identity), nudge.py, lk/ + lkrun.py + lkstage.py (a scratch copy of the likeness
    agent's module on this worktree's code), t1.py (tests one by one with peak RSS), r8.sh / r9.sh (all rows + table).
    - Integrity is judged against the INPUT (`_guarded`, `_newly_broken`, GUARD_WORSE 8%, GUARD_MM 0.1 mm; the
      STRETCH_MIN rule above is gone): a 3 cm chin drop is refused, the width fit passes.
    - `fit_outline`: ears ride in two passes (first solve, the mean move over each ear laid on it, holds within
      EAR_FREE let go, re-solve): 75% of the width miss passes unforced; it still stretches auricle edges ~0.9-1.03.
      Too wide for the eye: 75% + a moved jaw read as a bulldog. v20+ are built on the 50% head.
    - `base.head.shape.jawline` {below_lobe, forward, out, tuck, neck, sharp, smooth, top, radius}: on the bound head
      the mandible's visible edge IS GNM's jaw contour (lm 2-7), one diagonal from the lobe to the chin; the point
      shape.jaw_angle bumps is neck skin behind that edge. The control carries that LINE onto an L (under the lobe ->
      ramus -> angle -> straight border to lm 7 / 9), skin following by nearest stretch of line (`sharp` = how far
      along the line the turn is spread: 4-5 mm crisp, 14 soft), then tucks the band outside it and narrows the
      neck's sides under the corner. Dead ends: a Gaussian move of the "angle" (hidden: no change), filling skin out to
      the jaw's side per vertex (a folded flap). Corner height: believe the FRONT PHOTO (31-41 mm under the lobe);
      the painting's camera is loose (its 63 mm gives a boxy front).
    - `shape.ears` {out, size, blend}: a RIGID turn of the auricle about its attachment line (lobe's attachment ->
      top of the front attachment), the attached ring held: the top swings out, the lobe stays. The first version
      (turn about the root's main axis + scale, wide blend) made fins with a web of skin: auricle edges p95 1.74 vs
      1.39 now, protrusion 25 / 24 / 20 -> 17 / 13 / 12 mm (pass 6: 10 / 11 / 10).
    - `shape.nose_tip` deg | {up, reach, round}: the nose's BASE line tilted about the line through the alar bases.
      Measured in the desk view (alar base -> underside of the tip against the image's horizontal): painting +9.3 deg
      by my points (likeness reads +3: hand points are +-1.5 px), pass 6 -1.5, up 16 -> +8.9 (+7.1 after `round`).
      A turn about the mid dorsum only swings the base forward (the tip lies BELOW that pivot): 0.5 deg for 16.
      MediaPipe on clay renders does not track nose profile changes: don't fit the nose's profile with it.
      `round` = shrinking smoothing at the tip and supratip (a point with a notch -> a blunt end).
    - `shape.chin` {width, square, project, height, under, cleft, cleft_length}: mental corners apart, bottom
      levelled, chin forward, submental skin lifted (the chin-to-throat line runs back level, then down), a mid-line
      groove. `humanfit.fit_region` (GNM identity inside a feathered region, step cut back until integrity holds)
      exists; on the nose with MediaPipe targets it held at share 0.4 with little change.
    - Eyes: the likeness "eyes" stage (solve eye_width / eye_spacing + fit_hood) + nudge eye_outer made v19's sad
      slits; the photo squints 0.70 / frowns 0.64 (expression). v20+ carry HALF in identity (fissure 32.2 -> ~30,
      hood 4.2 mm, outer corners -1.3 mm, mouth corners +1.6 mm); the rest belongs in pose and is applied nowhere.
    - om_garrett: v16 pass 6 (fallback), v17 50% width, v18 75% + old ears, v19 first jaw L + full eyes (worse from
      the front), v20 rebuilt on 50%, v21 corner at the photo's height + chin + round tip (exported:
      /mnt/data/hifipushie/onemesh2/exp_garrett7), v22 chin projected 5 mm / under 16 / cleft 3, neck 11, sharp 4,
      brow ridge +3 mm (push_more), out -6. v22 is NOT exported and NOT judged on likeness's six-view read.
    - Open: lower lip height -3 mm and mouth width -4 mm (solve refuses past 57: v23's lip corners); the chin's
      bottom is a small hook in profile after `under`; brow ridge by a push, not judged; face width at the mouth
      went back to -8 mm on v21 (out -12; v22 uses -6: re-read); the profile-contour fit (likeness.fit_profile,
      trace in workspace/lk_garrett3/likeness_points.json) not run on om_garrett; squint / frown as pose.
  - Neck hand-over + the reset (2026-10-08, same agent; sheets human_renders/om2_r9_neck_seam.png, om2_r9_garrett.png =
    per reference: reference | pass 6 | new | 50% blend, lit with his locks, + the six-view sheet; scratch:
    neckdiag.py <model> <png> [variants: full | plain | "no X" | "only X"] (the neck in four views with raking light per
    variant), levdbg.py (GNM ring levels vs height), reset.sh (pass 6 + one change at a time -> om2_s0..s4 with their
    six-view sheets), six.py, readstore.py (store blind reads read_<model>.json, print likeness_read.diff), bigsheet.py,
    folds.py (which faces an edit turned over, where), read_form.txt).
    - THE SEAM (the user on the six-view sheet: "are we using the unified mesh? There's a hell of a seam between head
      and neck"): the mesh is fine (a plain one-mesh head is smooth). Adding Garrett's settings one at a time: head_size
      1.138 alone = a collar ring all round; the dense-fit warp alone = a shelf at the nape; `fit` a thin step; shape /
      identity / regions / narrow alone: smooth. Cause: the head's own shape was handed over to the body's neck over
      the asset's g_fade = 7 rings (~2.7 cm) above the stitch. Now `onemesh.neck_fade()` (NECK_RINGS 10 at the throat,
      ending under the chin, 20 at the nape, by how far back a vertex lies; never above g_fade), used by `hook` and
      the style's head ops; onemesh.VERSION 9. By HEIGHT it did nothing: GNM's neck rings climb toward the nape, so
      the nape had no length. Garrett: stature 180.6 -> 180.2 cm, interocular 69.8 -> 69.2 mm (the throat and nape
      take less of the head's scale). g_fade is still what face shapes' carry uses.
    - THE RESET (the coordinator, after v19-v22 read as "a different man: heavy, thick-necked, soft"): back to pass 6
      and one change at a time, each read BLIND (a fresh sub-agent given only likeness_read.form() and that model's
      six-view sheet; never read your own render with the reference in mind), descriptor-views kept of 62 against the
      reference read: pass 6 24, + rigid ears 35, + nose base / round tip 27, + chin 39, + jaw corner at the photo's
      height + submental lift 40. ONE reader per head and the noise is ~10 (the ears step "fixed" the jaw read, the
      nose step "lost" it): use several readers (likeness_read.agreement) before trusting a step. Consistent across
      readers: profiles go from "soft jaw, receding chin" to "square jaw, strong chin" only with jawline + chin.under;
      the chin reads broad with shape.chin. Never achieved: "snub / cute" nose, a visible cleft, "chunky" (every
      reader says lean). om_garrett v23 = that reset (v16 pass 6 stays the fallback). Exported:
      /mnt/data/hifipushie/onemesh2/exp_garrett8 (30k / 2048, rig + face shapes, 1110 s, Khronos 0 / 0, no TORN, shape
      unevenness <= 0.13, blink lid jag p95 0.96 / 0.89 = exp_garrett6's; sheets om2_r9_shapes.png, om2_r9_rig_head33 /
      _nod.png: the neck turns and nods as one column, no seam).
    - What LOCAL WARPS did wrong on this head, each caught by eye, not by the numbers (likeness had them "in
      tolerance"): the face-width outline warp at 75% + a moved jaw = a bulldog lower face; the eyes stage's full
      narrowing + tilt in identity = sad slits (the photo squints 0.70: that is pose); ears turned about the root's
      main axis with scale and a wide blend = fins with a web of skin; a nose tip turned about the mid dorsum = no
      change, then about the alar bases = a beak until rounded; jaw tuck 10 mm = a mask's edge; the jawline folded
      tiny faces by the lobe until its top was held. The method question (macro sliders in the identity space instead
      of local warps) went to the "refstudy" agent: no more face fitting on this branch.
  - Open: the head's 46 mm leak onto shoulder skin at Head 33 (rig thread); own quads cost a fixed ~40.7k body
    triangles; dense_fit as a tool (a GNM head as the target of human_reference).

- Face sliders (2026-10-09, "facesliders" agent; the user: "If we need more control around the eye area, we will have to
  update the mesh and/or sliders on the one-mesh, we should not just randomly sculpt"; sheets human_renders/fs_*; scratch
  DURABLE /mnt/data/hifipushie/facesliders/: run.sh <script> (spikes/facesliders/), tests.sh).
  - LOOPS (`gnmloops.py`, test_gnmloops): three edge loops cut down the middle of the closed edge rings 5.4-7.2,
    7.2-9.3, 9.3-11.8 mm above the upper lid margin (template): 530 vertices APPENDED (GNM ids 17821+, asset ids
    after 25847; 12 quads where the rings cross at the inner canthi cut in four), each the mean of its parents.
    `base._gnm_data` and every fit / Laplacian / binding stay GNM's; the loops are cut in at the end of
    `onemesh.template` (old vertices bit-identical; the built field moves <= 0.026 mm). The asset is extended at load
    (`extend_asset`: weights = parents' bones, uv per corner, faces = first child keeps the index); `gnm_id` of a new
    vertex = its first parent (lookups in GNM tables), `gnm_exact` = its own id (face shapes by index interpolate via
    `gnmloops.take`; retopo / asset masks via `raw_id`). HIFIPUSHIE_NO_LOOPS=1 builds without them. onemesh.VERSION 10.
    Garrett's rows above the lashes: 5.9, 6.5, 7.1, 7.8, 8.6, 9.9, 11.2, 14.9 (was 5.9, 7.1, 8.6, 11.2, 14.9).
    Export: "wrap" topology exports the quads as they are (+530 vertices, +~1060 triangles); the decimated path keeps
    its budget. No character LODs exist.
  - SLIDERS (`faceslide.py`, test_faceslide): base.head.sliders {name: v | [right, left]}, morph targets on GNM's
    template + loops (GNM frame), authored from the template's landmarks (u along the corners, h over the margin's
    parabola), added in base.gnm_head right after the identity (landmarks and every later op ride; the loops' own
    share goes through gnm_head["loop_offsets"]). Every field is held off the lids' rims (3D distance from the
    exterior skin's edge round the eye: a ramp in h alone turned the margin's 0.3 mm rows over), and the canthal tilt
    turns the fissure about the eyeball's forward axis (lifting the corner region opened a slot). epicanthal is one-
    sided (GNM's mean has none). `read_eyes` (crease from luminance up the lid in a clay render, tilt / opening from
    the projected rim) + `fit` (least change, central differences through humanfit.state, so through the loops):
    crease height 0.6 / -0.5 and canthal tilt -0.5 come back within 0.01. The crease reader needs a defined crease
    (eye_crease_depth > 0): on the template's soft lid the darkest line jumps. likeness LEVERS: canthal_tilt,
    upper_lid_show, under_eye, brow_ridge, prof_brow_ridge now drive sliders.
