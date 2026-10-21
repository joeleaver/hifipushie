# STATE: collar_spike (a folded shirt collar from the PATTERN's own pieces, on a primitive form) -- 2026-10-21

GOAL (Joe): a quick loop (seconds to a minute per look) that puts a folded shirt collar on a body from the PATTERN's
own band + collar pieces, closed and worn open, so that it matches the concept's open collar (Joe's trace:
/mnt/data/hifipushie/collar_spike/joe_trace.png, the concept is
workspace/garrett_v20/concept_v8_front_apose.png: open neck V ~60 mm below HPS, the collar's leaves stand either side
of the neck, long points ~147 mm apart, 50-61 mm below HPS). Primitive form only (Joe: Garrett isn't needed).
Spike only: no garment rounds, no agents grinding for an hour.

## What Joe settled (don't re-litigate)
- The pattern already has the right SHAPE (Simon's stand + collar from FreeSewing). Don't re-draft or invent the
  collar shape (the drape op, docs/state/drape_band.md, invented it; parked). The problem was always putting the
  pattern ON the body.
- "Can a flat piece make this" is the wrong question: any worn shape flattens to some pattern.
- A collar is NOT floppy cloth: the band and the collar are interfaced, pressed pieces. The settle must treat them as
  stiff (real bending stiffness), not as drapey cloth under gravity.
- The collar's flat fronts / points do NOT sit on the chest. Worn open they are held off the body by the collar's own
  stiffness, the band and the fold.
- The open look comes from the top button undone and the band's ends spreading, with the shirt fronts rolling back
  (C134), not from a neckline shape invented by hand.
- No enterprise / closed-source tools. GarmentCode (MIT) may be tried in another session. Avoid overengineering.

## Where it stands
- /mnt/data/hifipushie/collar_spike/wrap.py '{"tag": .., "open": deg, "grav": .., "stiff": .., "stiff_collar": 0|1}':
  loads Simon's stand + collar pieces from /mnt/data/hifipushie/drape_band1/form_c0.pkl (pieces["pieces"]["stand"
  | "collar"], names: stand leftBottomCf..rightBottomCf = neck edge, leftTopCf..rightTopCf = top; collar
  leftBottomEdge..rightBottomEdge = sewn edge, points at left/rightTopEdge), meshes them, wraps the stand round a
  neck cylinder (neckline = the stand's neck-edge length, 440 mm) over a shoulder cone, hangs the collar down
  outside, and relaxes with a home-made position-based solver (edge lengths, pins, sewing, floors). ~15-40 s / look.
  Renders front / three-quarter / side via hifipushie.render.render_views (clay_studio.exr, part colours).
- Results: CLOSED reads as a folded shirt collar (w3, w9, w12: band blue, collar orange). OPEN is wrong (w13: a hand-made
  open neckline drags the band into a deep V; band strain 100 %+). With fake stiffness (pair-distance constraints)
  and no gravity the collar still lies on the cone and wrinkles (w16): the start pose hangs it onto the body, and the
  pair constraints crumple a curved piece. Collar strain p99 ~22 %.
- spike.py (same folder) = the drape op on the same primitive (c1-c5, o1-o2, v1-v2): parked.

- 2026-10-21 Blender cloth try (bsim.py + bl_cloth.py, same folder; `bsim.py '{"tag":..,"frames":..,"bend":..,"tension":..,"sew":..}'`,
  Blender 5.1 headless, ~10-50 s): flat pieces as the rest shape key, a wrapped start, the band's neck edge pinned,
  sewing springs collar -> band top, self collision, little gravity. Faults found: wrap.py's start was stretched 60 %
  p99 with sliver edges (remeshed: outline at 5 mm + hex fill); the shoulder cone cut through the band at CF (moved
  below the band: pieces then hold still, 0.1 %). With the seam springs on, every run crumpled (b7-b10: strain 22-170 %,
  b10 the collar balled up). Joe: "not sure simulation is the right path"; two tries then regroup -> STOPPED.
- s1 (no sim, frames 1): each flat piece wrapped ISOMETRICALLY onto the surface it makes: the band (nearly straight,
  its neck edge an arc of radius 2.1 m) on a cylinder r 70 mm; the collar's sewn edge is an arc (radius 369 mm, fit
  err 0.7 mm), so the collar is an annular sector and wraps onto its own cone (half-angle 11.6 deg), turned down
  outside the band. 0.0 % strain, reads as a clean closed turned-down collar standing off the neck. Faults: seam gap
  up to 34 mm at CF (the band's top dips toward CF; the collar's sewn edge is 426 mm vs the band's top 445 mm), not open.

- geo.py (no sim, `geo.py '{"tag":..,"spread":deg,"drop":deg,"ramp":m}'`, ~15 s with render): bsim's isometric wrap
  (remesh now keeps every outline point: band top 441 = collar sewn 441 mm) + the collar shifted onto the band's top +
  OPEN = each front turned about Simon's own hinge marks (~65 mm back from CF). g1 closed: band 0.0 % / collar 2.8 %,
  seam 7.8 mm p99: clean turned-down collar. spread alone (g2, about the band's ruling) keeps the band at 1.2 % but the
  collar at 23 % (its cone's rulings don't line up with the band's hinge); drop (g3-g5) stretches 46-80 %. g3
  (spread 40, drop 30): points 120 apart (147), 63 below HPS (50-61), V 35 (~60); reads open-ish, twists, lies low.
  Lesson: moving stiff pieces by hand without stretch is the hard part (Joe's question); our strain counts SHEAR as
  stretch, but woven cloth shears freely on the bias (tailors shape collars with the iron) -> measure warp / weft
  strain, not edge strain.

- arap.py (no sim, `arap.py '{"tag":..,"spread":deg,"drop":deg,"pt":[apart,below_hps,standoff]}'`, ~15 s): geo.py's
  closed pose, then hifipushie.correctives.arap (existing, cotangent ARAP against the flat pattern) with handles only:
  band = back neck edge (CB..hinge) held + each CF end edge turned out / down; collar = sewn edge on the solved band's
  top (by arc fraction: snapping two sewn vertices to one band vertex read as 100 % strain) + optional point handles.
  a1 (40 / 30, collar free): band 12.8 % / collar 11.4 % (g3 rigid: 46-59 %), reads open, leaves fold in toward CF,
  points 92 apart. a2 (+ points pinned 147 apart / 55 below HPS): front silhouette closest to the trace, collar 53 %.
  a3-a6 (spread 70-100): strain 5-10 %, points 115-132 apart, but past ~70 the band front swings edge-on (inside shows).
  Open faults: the band ends' move is a guess (turn about the hinge); no shirt fronts, so the V can't be measured;
  ARAP has no bending term (correctives.py: kinks held tubes).

- Delamination (Joe: "is it coming delaminated?"): yes. ARAP holds only the seam, so the fold is a free hinge and the
  fall swings off the band: share of band verts with the collar >10 mm away: g1 0 %, a1 5 %, a2 24 %, a6 12 % (a6 also
  11 % collar inside the band, 22 % of the upper band uncovered). Fix tried (`lay`, default on): collar verts within
  the band's height of the sewn edge (flat) pushed radially onto the band + 2 x 1.5 mm, held, re-solved x4 (snapping to
  the nearest band vertex collapsed neighbours: 100-190 %). a1L: 0 % off / 0 % inside / 0 % uncovered, but collar
  strain 11 -> 19 % and dents + a rippled outer edge where the held region ends (hard holds crease ARAP).

## 2026-10-21 later: the SHIRT on an average body (Joe: "swap the simple form for an average human, start building
the shirt on these principles"). Files: /mnt/data/hifipushie/shirt_spike/ (run.sh <script> [args] = this worktree's code
under bin/capped; base_fit.py <tag> [json overrides] = pattern_form.on_form, the existing no-sim fitter, on workspace
wf_simon: MakeHuman 35 y / 1.78 m / weight + muscle 0.5, its Simon shirt; ~15 s fit + renders; sheet.py <tag>;
sym.py <tag>: mirror symmetry per piece, noise floor = mesh spacing, 1-8 mm).
- s0 closed (KB default "no_tie": collar button undone): reads as a shirt (Joe: "we almost one-shotted this"), strain
  2.5 / 11 % p50 / p99; the collar's FRONTS mangled + lopsided: collar mirror mismatch p95 34.6 / max 47 mm.
- Cause (Joe suspected mirrored rotations): not a sign error. garment_kb.json kinds.shirt.wear.no_tie.folds declares the
  two open-neck rolls ASYMMETRICALLY: open neck.L to buttonhole1+20 mm, .R to button1+60 mm (a ZOZO-era note: the over
  front's roll shortened so it doesn't cross the band's inner row). L fold row stretch 21 % vs R 2 %.
- s2 (both to +60 mm, overridden in memory, KB file NOT changed): collar mismatch p95 6.4 / max 13.6 mm, L row 7.4 %;
  clean, symmetric turned-down collar; still stands high round the neck, points close at CF (not the concept's V).
- s1 (Garrett's worn_open cfNeck 30 mm + his closures / folds copied): collar stands up round the neck like a wing, V
  crumpled, chest shows through: the same fault as Garrett shirt round 12.

- Collar (Joe: "specifically on the collar, we don't have that done yet"): s2's CB section had the 180 deg turn split
  into two 90 deg kinks 9 mm apart (a flat shelf on top; cover 2 mm). Cause: collar + stand meshed at 5 mm, the roll's
  radius 3 mm (2 triangles per half turn); radius / strength dead levers (s3 = s4). m2 (collar + stand h 2 mm via
  mesh_refine): one rounded roll, sections 172 / 169 / 176 deg, cover 5 mm at CB, fit 27 s: a believable collar with
  the collar button undone (KB no_tie). Ledger C137 (mesh vs roll), C138 (mirrored declarations).
  Tools: faults.py (per-piece strain / inside / off / open seams), crops.py (REG=collar: 5 collar views clay | strain),
  csec.py (sections round the neck: band, fall edge, cover), cbprof.py (the CB section's vertex walk).
  Other faults seen, not worked (Joe: collar first): sleeve ends crushed (99 % max, ~40 verts inside each arm), yoke
  at the side neck 13 % p99.

- Throat (Joe's arrows: the band ends at CF; "maybe it's in the pattern?"): m2's stand ends tipped ~45 deg out, collar
  front edges ran in over them. NOT the collar_spread rule (p0 spread off: same). Cause: the KB no_tie open-neck roll
  (neck -> button1 + 60, flap cfNeck, turned 170) puts the whole front neckline, where the stand is sewn, on a flap
  folded back. n0 (rolls removed, collar + stand h 2 mm): clean closed collar, stand ends upright 8 mm apart, points
  meet at CF, mirror p95 1.4 mm, strain p99 9 %. Ledger C139. n0 = the best closed collar so far.

- Joe's photos (open shirt, button-down): the placket edge runs straight up into the band's end; the front rolls back
  SOFTLY, the band turning with it; band ends lean apart; leaves stand off the neck. Simon already has it (C139): band
  extensions 9.3 / 14.8 mm = the plackets 9 / 12-15; ours left them unsewn (seam table CF..CF) and cut them
  (band_ends). e0 (Simon's seam edge to edge, band_ends off) flipped the fall INSIDE the band: _turn_flaps ranked a
  near-tie on the unsigned angle first (C140, fixed in pattern_form: FLAP_OUT_FIRST). e1: band ends flush with the
  placket tops, clean closed collar, mirror 1.3-1.7 mm p95 = the best closed collar. Softer rolls alone (r90-r150)
  don't open the neck (band ends stay 7-11 apart). o-runs (worn_open + Garrett closures) refused: the roll line's end
  falls 13 mm inside the front with Garrett's button spacing.

- OPEN state (Joe: "let's look at open state, we're doing well"). The fitter's worn_open (oA-oD: cfNeck 30 / 45 mm,
  Garrett's closures) parts the band's BOTTOM corners (60) while its tops stay knotted (11): every lever tried was dead
  (collar_spread, OPEN_SPREAD already off, no closure / centre-line pin holds them). Own staged ARAP with the CLOSED fit
  as rest (openarap.py: oa*, ob*, or*) can't open the ring either (rest curvature) and tore (in-plane edge handles
  crush the band). flatarap.py (NEW, the working one): per-face ARAP against the FLAT PATTERN (each triangle its uv,
  Liu 2008 local / global), sewn pairs welded, bending free, staged from the closed fit e2 (e1 + Garrett's closures).
  Handles: held back / yoke / sleeves / fronts below the first fastened button; collar points to the concept (147
  apart, 55 below HPS); each band end swung like a door about Simon's own hinge ruling (swing deg). fe3 (swing 50):
  strain vs the pattern p50 0.3 / p99 4.4 %, band ends 73 / 53 apart, an open V, band ends upright with the placket
  edges. vs Joe's photo + trace: leaves splay out flat (his stand up beside the neck), V too deep (to button 1, ~98
  below HPS; concept ~60), fronts don't roll back (taut at the V). Two more mirror bugs found on the way (my own
  in-plane turn sign; a side taken from x at CF where the band ends cross): take the side from a landmark well off CF.

## NEXT
(1) Joe's calls (repo changes): simon seam edge to edge + band_ends off (C139); remove the KB no_tie open-neck rolls;
FORM_REFINE_SHIRT collar + stand h 2 mm; (pattern_form FLAP_OUT_FIRST already in, C140).
(2) Open state on flatarap: first fastened button for THIS body at the concept's 83 below HPS (closure spacing, not
Garrett's 47 from cfNeck); collar points' targets standing off the chest (stand_off) so the leaves stand beside the
neck; the fronts' soft roll (a fold row from the band's end down to the button, or a handle on the front edge);
fix openm.py's V read (reads 196). Then a blind review vs the photo / trace.
Rules: renders under /mnt/data/hifipushie/bin/capped (GPU lock); files on /mnt/data/hifipushie/; stage git by path,
never `git add -A`; only the coordinator pushes main.
