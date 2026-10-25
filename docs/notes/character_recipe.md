# Recipe: a new realistic game character (2026-10-19)

A working recipe, in stage order, built from what Tess and Garrett taught us. It is not history: history is in the
thread notes (grep only). Every lesson behind it is a row in docs/notes/codified.md; symptoms that fooled us are in
docs/notes/traps.md: read that before you trust any measure.

## Rules for every stage

- The four gates (docs/notes/gates.md): DESCRIBE the reference as measurable items in
  `workspace/checklists/<piece>.json` -> MEASURE every item every round (item | reference | ours | pass) -> LOOK with a
  blind reviewer (`/mnt/data/hifipushie/bin/review <out> "<region>=<ref_crop>:<result_crop>" --stage ... --not ...`)
  -> APPROVE (Joe, or the coordinator from a reference-beside-result look: `bin/approve add <stage> <piece> ...`).
  The next stage consumes ONLY `bin/approve get <stage> <piece>`, never the newest file.
- Keep / revert by `bin/review-ab` (both candidates, same tiles, one sitting). Exit 4 = the review did not run; it is
  never 0 MAJORs. Before 13:00 MT the CLI is rate-limited: use a fresh blind subagent on the same trios + key.json.
- STOP-LOSS (all stages): a fault gets at most two rounds without a visible change on its own before / after tile.
  Then change the METHOD (write it up first) or park it with its evidence. After two failed fixes of a shared default,
  go back to the last known good and make the new behaviour opt-in.
- Measures: validate on a known case (reference against itself, a planted fault) before one drives a change. Prove a
  lever moves its row on the cheap path (a saved dump, one part, ~1 min) before any batch.
- Looking: single-feature crops, reference beside result, scale-matched, ~400-480 px tiles. Full sheets only for Joe:
  reference | best result | others. Look at pairs before reading any caption or number.
- Game assets are judged at game distance too: 1 m and 3 m, 1920x1080, native pixels; close-up-only MAJORs are logged,
  they don't block. Likeness under the reference's fitted light (stage.photo_light), readability under the game rig.
- Machine: heavy jobs `resources.heavy` with the real GB + `/mnt/data/hifipushie/bin/capped` (renders take the GPU
  lock); light sweeps `bin/slot`. Durable files on /mnt/data/hifipushie. Never push; stage by path.
- Private heads: nothing of them in the repo. Critique the model, never the person.

## Stage 0: references and the DESCRIBE checklist

Inputs: the pictures (photo / painting / generated), what Joe said about the person.
Defaults:
- Per picture: kind, view and whether its stated angle holds, lens (EXIF), light, expression, what it can't show, and
  which picture is the authority per item (the front for colour). Handed refs: measure what they support, mark the
  rest INFERRED with confidence; never block on a missing view. Refs we generate: a shot brief from the checklist.
- The person in words: sex / age read, build, the 3-5 masses and planes that make this face (blockin_guide "Stage 0").
- Measurable items per feature (likeness checklist): face width / height ratios, eye spacing and opening, nose width /
  length / tip, mouth width and lip heights, jaw and chin, brow ridge, profile points; `face_ruler` reads most in mm.
- Ask Joe for a STYLE reference if the look is anything but realistic ("stylized" means a different thing per model).
Gate: the checklist exists before any template or default is chosen. APPROVE stage "references".
Traps: photo masks that drop highlights (traps.md "Photo hair mask errors").

## Stage 1: body build

Inputs: the references, the body build Joe asks for (Tess: "average slender young woman, not weird").
Defaults: the one-mesh human (`human` tool, `base.source` "human"); pick body macros by MEASUREMENT:
`body_check.percentiles` against ANSUR II (age band 18-30 for young adults), aim for a balanced band with no outlier
(Tess: p20-35), flag anything under p1 / over p99. Parametric sources before any hand edit.
Gate: body_check table + a whole-figure sheet; Joe confirms the build (TASTE). APPROVE stage "body".
Stop-loss: an extreme body breaks every garment draft: fix it here, never in the cloth.

## Stage 2: head (artist block-in + joint solve)

Inputs: approved references, approved body. Guide: `guide(topic="block_in")`, sub-topics blockin_solve / blockin_steps.
Defaults:
1. `block_in_start(name, refs, sex=...)`: GNM's class mean on a GNM-NATIVE head (GNM's eyeball, teeth, mouth, tongue:
   use what GNM ships). Never start from a previous fit.
2. `face_ruler(name)` first and after every step.
3. `block_in_solve(name, cameras=...)` 3-4 calls until |dc| < ~2-3, stop at the first DAMPED step. cameras="trust"
   when the refs' cameras are good, "refit" on the first call when kept cameras came from another head, else "free".
   Read AT THE BOUND / DISAGREE / MOVED WITH NO READ (treat those as INFERRED).
4. Hand steps for what the solve can't read (cheek volume, lid fold, nose planes): squint, name the single biggest
   mass / plane difference, look it up (`gnm_controls(phrase=...)`), `block_in_step(name, {dir: amount}, seen=,
   why=)` 0.3-0.7 sd; keep a step only if the whole face reads closer. The solve is the base; you finish.
Gate: MEASURE = the likeness items at the reference cameras. LOOK = the judging sheet (photo | 50 % blend | the
references projected as the head's skin | own dressing: spikes/reruns/jsheet.py) plus feature tiles
(spikes/tour/tour.py, blockin.focus), judged by perceived identity (face-ID embedding between our renders), not mm.
Joe approves the head (stage "head"). From here on the head GEOMETRY is frozen.
Stop-loss: local slider tweaks one feature at a time make faces uglier: if two hand steps don't bring the whole face
closer, rerun the joint solve from the class mean with the new evidence instead.
Traps: whole-head sheets hiding feature faults; a profile camera's yaw is the least pinned thing (check it first).

## Stage 3: skin (textures only)

Inputs: the APPROVED head (by name). Guide: `guide(topic="skin")` (stages 0-9 table, skin_layers for keys).
Defaults:
- `skin_from_reference` / `skin_project`: the pictures are a MEASUREMENT driving the layer stack (tone, zones,
  features, brows, stubble, eyes, folds); the photo's pixels don't ship.
- Tone through the pigment model (`tone` melanin / blood), read from the authority picture's forehead box; lightness
  isn't observable without an exposure anchor: anchor it. On a stacked head skin.tone is the body.
- Folds (`skin.folds`: lid_fold, tear_trough, nasolabial ...): relief <= 1 mm is skin (Tess's lid_fold .6 = 0.51 mm).
  More than 1 mm is head FORM: it goes back to stage 2 with its own A/B and Joe's approval
  (asset.FOLD_FORM_MAX_MM clamps and warns on the export branch).
- One lever per step (lips: melanin at strength >= 1; brows: thickness, opacity, soft one at a time against brow L).
- Lashes >= .12 mm thick. Judge in EEVEE under PBR Neutral, at the face resolution the export meshes, then in the GLB.
Gate: MEASURE = the skin items (L*a*b* in named boxes, brow L, lip L / a* / border, mottle, beard rows) on feature
tiles. LOOK = review per feature, scoped `--stage skin`. CURRENT BEST changes only by review-ab. Joe approves the
skin (stage "skin"); age texture beyond the approved head and iris colour disputes are his calls.
Stop-loss: a feature that two skin rounds don't move is probably FORM (e.g. Tess's ala blotch = nose form, no crisp
alar groove): route it to the head stage, don't paint over it.
Traps: AgX vs PBR Neutral; dead levers under an opaque layer (print the layer order); skin threads reshaping the head.

## Stage 4: hair

Inputs: the APPROVED head; the hairstyle described first (hair_guide / hair_checklist: style in words, parting,
hairline shape and height, temple corners, volume per region, lengths, lock separation, colour front vs back).
Defaults:
- Long / tied hair: a strand groom (`groom_hair`, `tie_hair` for tied styles, `look_hair(views="around")`), then CARDS
  cut from it. Crown: the arch row + the fill under it are defaults (hair_clumps.ARCH = 4, ARCH_FILL = 1;
  hair.ARCH_TIERS carries them to LOD1-3). Back faces as their own triangles + single-sided material
  (hair.BACK_FACES = 1). Tess's best flags: docs/state/tess_hair.md. NOTE: `hair_clumps.FILL` is the bake's packing
  share, not the crown fill (traps.md).
- Short cuts (< 6 cm mean lock, hair.SHORT_TIERS): a cap baked from the strands + shells over it
  (`hair.export.style "shells"`, branch hair-heads2) + hairline / sideburn row cards (`hairline_row`). Garrett's sh4T
  build: docs/state/garrett_hair.md. Cut-per-clump cards read as torn paper on a crop.
- Carry an approved groom onto a new head lock for lock (`tie_hair(name, carry_from=<approved groom>, reseat=True)`), never regrow it.
- Budget (budgets.json hair_cards: hero default 25k, range 15k-50k): see the open decision in codified.md row A8
  (card faces vs drawn triangles); whichever is in force, report card faces, drawn triangles and vertices per tier.
- Hair module constants are not spec keys: set them in ONE script that the export also runs.
Gate: the GROOM is judged against the photo (its own stage, Joe approves "hair"); the CARDS / shells are judged against
the approved groom render at the same camera, light and head (source-asset scope), in EEVEE only, at 1 m / 3 m.
Adopt builds by review-ab against the current best.
Stop-loss: card changes can't fix a fault the groom has: after two rounds on one fault, check whether the groom shows
it too and route it there.
Traps: half-sided preview; judging cards against the photo; photo mask errors; the LOD0 tier "helmet".

## Stage 5: clothes

Joe 2026-10-20: "we need to be better at measuring up front." 34 garment rounds were mostly lost to things a flat
check would have caught (ledger C61 / C113 / C117 / M9-M11, docs/notes/measurements.md). Order, like a pattern maker
(process as of 2026-10-25: measure -> flat gate -> muslin fit -> styling as worn; no sim in the path):
0. MEASURE THE BODY FOR THE DRAFTS, before any draft: every measurement a draft consumes comes from the tape in THAT
   draft's definition (measure_defs: per-draft definitions with sources, adapters at the boundary; a draft refuses a
   measurement with no declared definition; gate row `measure_definitions`). A new garment kind or draft declares its
   measurements and their definitions first, with a synthetic-body known answer (tests/test_measure_defs.py). Read the
   values against the body: shoulder seam vs the body's neck point -> shoulder point (length + drop), neckline vs the
   neck base + the book's ease, hip line height, plumb girth. The neck point is where the neck meets the shoulder
   (FreeSewing's, hps "corner", C160, opt-in per garment). A fix left opt-in for one garment is checked against
   every garment that consumes the same measurement.
1. DESCRIBE big to small from the reference (checklist items with value + tolerance become gate rows, C103): opening /
   closure state, silhouette, length, collar state, then details. Physics vs art intent: a pose a real garment
   wouldn't take is reached by STYLING (C81, C142), never by bending the pattern. Ask Joe only what his rules don't settle.
2. UNDER GARMENTS FIRST (C85): a garment worn under another passes its own fit before anything is fitted over it.
   What a cover hides is culled (cloth_layers.hidden); judge the under garment where it SHOWS (C90, C115).
3. FLAT PATTERN gate (below): every visible part a cut piece or a sized mark (plackets, flaps, buttons); folds,
   presses and pleats checked by the generic fold family (C106) flat; tailoring rules with sources.
4. THE MUSLIN FIT IS THE FIT (C162; fit_garment, pattern_form, no sim): woven cloth on the form, threads held, bias
   shears up to the weave's jam (SHEAR_LOCK_DEG), a soft neck pin that never drags cloth to a landmark by stretching it
   (C161, C166, C167); misfit read as thread strain by region (C169). An open front is fitted with its break open
   (C171). Worn big reads measured on the fit (C104); fold family on the form; whole-front view first, then crops of
   what Joe flags (C52). No release sim: a sim is optional, a wrinkle source at most (C157 superseded).
5. STYLE AS WORN (fit_garment's wear ops / style_garment): pull until it would stretch (a THREAD strain or the shear
   lock stops it, C142, C169, C198); every styling ends with smooth + pull down (C174); a hand LETS GO after its move
   and what hangs free drops, the lower fronts hang (C199). Renders for Joe show the design state, never a stage.
6. SUPPORTS, NOT HOLDS (C190): hold only what physically carries the garment (shoulder / neck contact, sewn seams,
   fastened closures, layer contact), soft and named. Workaround holds made the pinch, the narrow hem, the side-seam
   cord and the rigid-grip creases (C186, C188, C189); PLUMB_HOLD (C181) is being replaced by the canvas default.
7. THREADS FIRST, THEN BENDING (C195): stiffness never buys shape with stretch. Collars and canvassed fronts keep
   their shape by drafted canvas / interfacing bending (C194, C196); floors have a side and floor cloth on cloth
   (C197, C200, C202). A trade-off between two goods means the model is wrong (gates.md "Coordinator").
8. LAYERS: the under garment fits first (C85); the over garment fits over it; covered show-through is not a composing
   fault (C153); the cull hides only what no judged view sees, plus covered poke-through (C158, C183, C187).
9. JUDGE beside the REFERENCE only: current / approved garments are never a baseline (C165). Verdict: overall standing
   first, then faults ranked by game visibility. Freeze (`cloth.freeze`); hand finish only small faults on the result.
Tools: `pattern_check`, `fit_garment`, `style_garment`, `review_view`, `judge_asset` (`dress` only as a wrinkle source).
Guide: `guide(topic="cloth")`. Threads: docs/state/canvas.md (the no-hold default), dress_garrett_fit.md, dress_garrett_shirt.md.

### Pattern gate (ENFORCED, 2026-10-19)
Joe: "we're spending too much time on sim before we validate our patterns." Before ANY sim of a drafted garment:
- MEASURE: `cloth_check.pattern_gate(model, garment, refs=<saved cloth_reference.read reading>)` drafts and places the
  pattern on the body (no sim: `cloth.build(place_only=True)`) and measures every cloth_checklist.json item of the
  garment's kind it can read there: seam ease / notches, lengths and widths on the placed rest, design choices, plus
  `neckline_standoff_mm` (INFO until a checklist item adopts it via "pattern_measure"). Items with no pattern-stage
  measure (a "missing:" measure, no reference reading) are UNMEASURED and block; drape / fold / worn-tell items are SIM
  (judged after the sim). Waive a row only by name with a reason (`waive={"id": "why"}`, recorded).
- LOOK: `sheet=True` (under bin/capped: GPU lock) renders the placed garment on the body, clay, front / 3/4 / side /
  back at ~1 m, the concept first: a pre-sim sheet a reviewer or Joe judges before any sim.
- The record (`/mnt/data/hifipushie/pattern_gate/<key>.json`) is keyed by the pattern's content hash + the body's hash:
  change the pattern and the record no longer applies.
- ENFORCED: every sim (cloth._blender_job local, cloth_job.run_zozo local / rented, run_external) refuses
  (SimNotSubmitted) without a PASS record, naming the failing / unmeasured rows. Override for the transition only:
  `HIFIPUSHIE_SIM_WITHOUT_PATTERN_GATE="<reason>"` (logged in the record, the job folder and overrides.jsonl).
- Pattern ops and construct option dicts that change a default carry `"source": "<where the number came from>"`;
  the gate WARNS without one (traps.md "A misread note became a pattern default").

Gate: measurement definitions and the pattern gate on the draft; the muslin fit judged for fit, silhouette and big
reads; the styled worn state judged in the game render at 1 m / 3 m. Re-freeze only when a blind review prefers the candidate.
Joe approves each garment ("garment").
Stop-loss: two failed levers on one fault -> measure it FLAT (lengths vs the body's surface paths, the measurement's
definition) before another form or sim lever (shirt rounds 1-6: neck levers on a shoulder-slope bug).
Traps: a shared landmark changed (HPS) sets off a chain: back to known good.

## Stage 6: expressions

Inputs: the approved head; a reference of a real person making each key expression.
Defaults: an expression is a MIX of the exported ARKit shapes / GNM expression parameters. Search the mixes; never
sculpt per-character deltas or hand-shape the result (HP_SHAPE_SCULPT stays unset). Starting point for a smile:
Tess's mix A2 = mouthSmile 0.8, cheekSquint 1.0, eyeSquint 0.5, mouthDimple 0.6, mouthPress 0.2, mouthUpperUp 0.108
(its limits, teeth band ~81 % of the corner span, weak exported squints, are accepted). A mix measured on one person's
fitted shapes is not the same smile on another: re-search per character. Fitted env inputs (HP_SMILE_FIT,
HP_JAW_FIT) apply to WHATEVER head is exported: clear them between characters (faceshapes.env_fits warns).
Gate: feature tiles per pose (mouth from nose base to chin, each eye with its lower lid, each cheek / nasolabial area),
aligned on the feature's landmarks, beside the reference expression; plus 1 m / 3 m frames. Lids close fully in the
blink, teeth / tongue / lashes follow. Joe approves ("expressions").
Stop-loss: fourteen hand-tuned smile rounds lost to a parameter mix: if a mix search can't reach a shape, report the
limit; don't sculpt.
Traps: proxy render in a different pose than the batch.

## Stage 7: rig and motion

Defaults: Mixamo-compatible (`rig.humanoid`, `mixamorig:` names); modelling bones are never exported as rig bones;
retargets corrected for the rest pose (A vs T). Judge bends at 45 / 90 / 120 deg (volume kept, garments and hair ride),
each clip beside the same clip on its source skeleton. Joe approves ("rig", "motion").

## Stage 8: export (game-ready GLB)

Inputs: ONLY approved pieces by name: head (`base.head_approved` = the approval key), skin stack, hair build, frozen
garments. Tool: `export_asset` / asset.export.
Defaults now in code or in force:
- Head geometry = the approved head's (asset.approved_head checks it; on the export branch, not main yet); skin
  textures only on top; folds > 1 mm clamped (FOLD_FORM_MAX_MM).
- Options: {"role": "hero", "lods": true, "cull_under_cloth": true, "cull_poses": "<pose npzs>"}; LOD0 hair tier from
  the role when hair.export.tier is unset (asset.hair_tier_default); LOD1-3 hair tiers lods.HAIR_TIERS.
- Budgets from budgets.json by role, for a mainstream GPU (not the laptop iGPU); triangles per LOD under the gate.
- Declare 24 GB to resources.heavy; run under bin/capped.
- Colour checks under asset.GAME_LIGHT (PBR Neutral) against stage references rendered the same way.
Gate: each piece in the export beside its own approved sheet at the same camera and light: must not be worse. The RC
changes only by review-ab with the approved stage as the reference. Specks / LOD diff checks on the GLB.
Stop-loss: a fault that appears in the export but not in the piece's own render is an export fault; one that the piece
shows too goes back to its stage (don't tune the export for a skin or hair fault).
Traps: UVs read upside down (trimesh is v-up); a bake probe on the wrong uv; per-character env leaking; drift.

## Stage 9: engine check and the final sheet

Engine: none (engine-agnostic). The exported GLB re-imported into Blender (glTF importer materials only), EEVEE set up
like a game: no Cycles, no ray tracing, alpha clip / hashed cards, blink map and face shapes driven, LODs at their
switch distances.
Final sheet for Joe: reference | the approved head / pieces | the build, same camera and light, 1 m and 3 m frames
plus the photo-lit close-up, each labelled with its light. Joe approves "engine" / "assembly". Done means every stage's
checklist passes, every review point is answered, and every piece is approved.
