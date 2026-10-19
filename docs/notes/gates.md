# Gates: every step, reference first (2026-10-14)

Why: game-ready Tess v2 reached Joe in a state he called "_terrible_": a sweater whose own sheet said CORRUPT
(a sweatshirt block, armholes nearly torso-deep, no knit), hair re-tied with defaults instead of the approved
groom, Mixamo clips retargeted without rest-pose correction (Gumby limbs). Every agent's own gates had passed.
Joe: "There's something seriously amiss in our pipeline that we allowed this to come through in this state."
"Not just the clothes, but everything, step by step."

The faults were in the PROCESS, at four points:
1. Gates measured what was easy (crossings, strain, coverage, validator errors), not "is this the thing in the
   reference". A piece can be clean and wrong.
2. Work started from the nearest template / default and fixed faults one by one. "Fixed the armpit holes"
   became "sweater fixed".
3. Nothing recorded what was approved. The next stage took the newest file.
4. Review was the author grading itself, then a coordinator reading the author's caption before the picture.
   "It runs end to end" was reported as a result.

## The rule: four steps at EVERY stage

1. **DESCRIBE** (before any work): write what the reference shows for this stage, in words and as measurable
   items, in `workspace/checklists/<piece>.json` (git-ignored: may name private subjects). Each item has the
   reference value (measured or read), how it's measured on ours, and a tolerance. Say which items are
   inferred (not visible in the reference). No template or default is chosen until this exists, and the
   choice is justified by the items ("a knit crewneck: set-in sleeve, underarm 2-4 cm below the armpit, rib
   bands 4 / 6 / 6 cm").
2. **MEASURE**: every item is measured on the result, every round, and printed as a table: item | reference |
   ours | pass. A failed item is the fault list; the author fixes the biggest one first. Tool gates (crossings,
   validator, coverage) are still run, but they're necessary, never sufficient.
3. **LOOK, by the agent itself, every round** (Joe: "the own agents need some sort of process by which they're
   like 'does this _look_ good? No it does not, here's what it needs, keep trying'"). Every round, the agent runs
   `/mnt/data/hifipushie/bin/review <out_dir> "<region>=<ref_crop>:<result_crop>" ... --context "<one neutral
   line>"`: a blind art-director review (a separate headless Claude) that sees ONLY reference | result pairs per
   checklist region, no captions, numbers or claims, and lists every fault MAJOR / MINOR with a "needs:" line,
   ending VERDICT PASS (no MAJOR) or FAIL. ~1 min. The agent fixes the worst MAJOR fault and loops.
   - Construction reviews (patterns, form / pre-sim sheets, drapes, layered garments) put the DIAGNOSTIC render
     (diag_render: panels + seams + turned; strain + layers) beside the clay one, both as review crops: flat
     colours make a kink, a fold on the wrong side, a flap turned into the body or a shirt through a jacket
     obvious, where clay shows only shading (Joe 2026-10-19). docs/notes/render.md "Diagnostic renders".
   - When a round trip is long (renders on NICO-TOP: ~1 h), one fault per round means one round per session. Fix
     EVERY independent MAJOR you can address in the same round (one change per region, each listed in the notes),
     then re-review all regions. "Worst first" orders the work; it is not one fix per round. Before fixing, group
     the MAJORs by cause (light / shader / paint / geometry / pattern); a cause shared by many faults goes first.
     (2026-10-15 audit of the skin sessions: ~30 MAJORs per review, one round per session, no passes.)
   - Many changes per round need a MEASURED target for each: a ratio or colour read from the reference crop
     against ours. The value comes from that measurement, not by eye. A row with no measure gets a small crop
     statistic first. Record target / before / after per row; revert a change that made its row worse.
     (2026-10-16 skin r3: ten hand-picked values per head; brows overshot to near-black, one head went 29 -> 42 MAJORs.)
   - A checklist that passes while the result still looks wrong is INCOMPLETE. Name what the eye sees that no item
     measures, add a measured item with a target from the reference, and only then change the model. (2026-10-16
     Garrett hair G56r: every item passed, but it read as a bristly crew cut; lay, length, tips and striping were unmeasured.)
   - Prove a lever moves its row BEFORE a round depends on it. Run a cheap local check (flat or ID pass, the fast proxy)
     with the lever at two values: if the measured row doesn't move, the lever is dead (plumbing, layer order, a cached
     attribute, a mask). Fix that first, and never send a dead lever to a batch. (2026-10-16 skin r5 / r6: lid_shade was
     dropped under a stack, then painted over; sheen moved nothing; assembly TONGUE_DOME. Each one cost a full round.)
   - FACES ARE REVIEWED ON FEATURE TILES (2026-10-18, coordinator after Joe: "Tess's smile is truly horrific"). Eleven
     expression rounds (r35-r45) sent whole 1 m frames to the reviewer: an 812x422 pair, the face ~150 px, the mouth ~40 px,
     the reference not scale-matched. No review ever named "grimace" or "lips not touching the teeth". For every face pose
     (smile, jaw open, neutral, squint ...) the LOOK input is single-feature tiles, ref | result, each aligned on that
     feature's landmarks (scale + shift) to the photo, the feature filling a tile of >= ~400 px, no captions: the mouth
     (nose base to chin), each eye with its lower lid, each cheek / nasolabial area (front, + 3/4 when a 3/4 photo exists).
     Tool: assembly scratch r46/tiles.py (MediaPipe, similarity per feature); spikes/tour/tour.py does the same for heads
     from the block-in. The 1 m / 3 m frames stay, but only as the separate game-readability check under the game rig.
   - Scope the review to the stage: `--stage "<what this stage owns>" --not "<other stages>"`. Faults outside
     the stage come back under OTHER STAGES, don't count toward the verdict, and go to the coordinator (who
     routes them; an approved piece is reopened only with Joe). Hide other stages' parts when they cover the
     region (e.g. skin crops without the groom).
   - Crops cover EVERY checklist region (a region left out is a fail), same framing both sides, big enough to
     judge (the reviewer says when it isn't). Never write claims into --context.
   - The agent answers each point in its notes: fixed (with the next review's pair), or disputed WITH evidence
     (e.g. the reference doesn't show it). It never overrides a MAJOR by its own opinion.
   - Nothing goes to the coordinator until the review PASSES on every region, EXCEPT: a decision that is Joe's,
     or STUCK (the same MAJOR fault survived 3 honest attempts with different approaches): then send the review
     history and what was tried, and keep working on other faults meanwhile.
   - The coordinator looks at the pairs BEFORE reading any text, and re-runs `review` on spot checks.
4. **APPROVE**: only Joe, or the coordinator from a reference-beside-result look, marks a piece approved in
   `workspace/approved.json` (`bin/approve`). The next stage consumes ONLY approved pieces, by the exact model /
   file named there. Anything else is "draft" and never goes into an assembly or to Joe as a result.

"Done" means the stage's checklist passes, the review's points are answered and the piece is approved.
A pipeline that runs end to end is a test of the plumbing, not a result: it's shown only beside the approved
sheets of its pieces, and each piece must look at least as good in it as on its own approved sheet.

## Stages and what each checklist must cover

References
- What each reference is (photo / concept / generated), lens, light, what it can and can't show, conflicts
  between references and which one is the authority per item (e.g. the front view for colour).

Head shape (block-in, hand passes)
- Per-feature likeness items (likeness checklist): face width and height ratios, eye spacing and opening, nose
  width / length / tip, mouth width and lip heights, jaw and chin, brow ridge, profile points. Measured at the
  reference cameras. The judging sheet (references projected as skin) is the LOOK input.

Skin
- Overall tone (L*a*b* in named boxes: forehead, cheek, nose, chin), redness distribution (where, how broad),
  freckles / pores / texture scale, lips (colour, border sharpness), under-eye tone, brows (shape, density,
  length), creases (height above lashes, smoothness, softness), iris colour, sclera, catchlight. Close-ups per
  feature beside the reference crop at the same framing.

Hair
- "Describe first" (docs/notes/hair.md, the 15-rule checklist): style in words, parting, hairline shape and
  height, temple corners, volume / stand-off per region, lengths, lock separation, colour range front vs back,
  coverage (no scalp where the reference shows none). Seated on the APPROVED head.

Garments (per garment)
- Garment type and construction (knit / woven, block, sleeve type, neckline, closures), fabric (fibre,
  weight, surface: knit gauge, twill, sheen), key measurements read from the reference against the body:
  lengths (hem, sleeve), armhole depth vs armpit drop, ease at chest / waist / hip, band widths, pocket
  placement, how it's worn (open, tucked, layered over what). Folds the reference shows (knees, stacks,
  elbows). Surface details that make it read (rib, topstitching, hardware). Pattern gates measure the DRAFT
  against these before any sim.
- Simulation judges fit, silhouette, hang and main folds only (about 3 draft + 2 final sims per garment). Then a
  FINISH stage: made pieces built on the drape, local faults finished by hand on the draped mesh (recorded edits on
  top of the sim), fine detail in maps. A review fault that a sculptor would fix in minutes is a finishing job,
  never another sim (2026-10-15, Joe: "Are we depending too much on simulation?").

Assembly (game-ready export)
- Inputs: the approved head, skin, hair and garments by name. Budgets (triangles per part, LOD shares,
  texture sizes). Each piece in the export beside its own approved sheet (same camera): must not be worse.

Rig and weights
- Mixamo names and rest pose. Bends at shoulder, elbow, wrist, hip, knee at 45 / 90 / 120 deg: volume kept
  (no tube bends, no candy-wrapper, measured twist), garments and hair ride without poke-through.

Motion
- Each clip (in Blender) judged beside the SAME clip on its source skeleton, frame by frame (retarget errors show as
  arcs, cocked wrists, arms held out). Silhouette per frame.

Expressions (ARKit)
- For the key shapes (eyeBlink, jawOpen, mouthSmile, browInnerUp, mouthFunnel...): beside a reference of a
  real person making that expression. Lids close fully, teeth / tongue / lashes follow, the crease fades.

Engine (none: hifipushie is engine-agnostic; Joe 2026-10-14: "It doesn't need a godot check ... Blender with
eevee built like a game would work is enough")
- The exported GLB re-imported into Blender and rendered in EEVEE set up like a game: the glTF importer's
  materials only (no Cycles, no ray tracing), alpha clip / hashed hair cards, the blink map and face shapes
  driven as an engine would, LODs at their switch distances. Beside the approved pieces' own sheets and the
  reference. No Godot or other engine in any gate.

## Game distance (assets judged as game assets: expressions, faces, hair cards, lashes; 2026-10-16)
Why: Tess's expression rounds ran ~14 reviews in a day on close-ups and the MAJOR count did not fall; many faults were
sub-millimetre (a 1 px dark seam at the lip-teeth line, a corner fragment). The lash work showed cards and ribbons
identical at 1 m and 3 m at 1080p. A game character is seen at game distances, so close-up-only faults can't block it.
- Every round on such an asset adds a GAME-DISTANCE set: each pose / expression at 1 m and 3 m from the camera in a
  1920x1080 frame (vertical fov ~59 deg, a 90 deg horizontal game camera), in the game-like EEVEE, crops at NATIVE
  pixels (never upscaled), the reference scaled to the same pixels per metre beside it. The photo-lit close-up stays.
- Each MAJOR is classified: GAME-VISIBLE (seen in the 1 m or 3 m crop) or CLOSE-UP-ONLY. Fix order: game-visible
  MAJORs first, grouped by cause. Close-up-only MAJORs are recorded in the notes but do NOT block the gate, unless
  they are also visible at 1 m. Hero cut-scene close-ups, when a game needs them, are a separate declared target.
- The 1 m / 3 m sheet goes to Joe every round (reference | best result | others).
- LIGHT (coordinator, 2026-10-16): LIKENESS is judged under the REFERENCE's light, game READABILITY under the game rig.
  Likeness views (front close-ups, the review pairs that ask "same person?") render under the reference's fitted light
  (stage.photo_light, the light the head was approved in); the 1 m / 3 m game-distance reads keep the game rig (hard key
  + fill + back suns). Both sets go on the sheet, each labelled with its light. Why: Tess's expression sheets rendered
  under the game rig's hard 3:1 side key while the approved head was judged under the photo's soft fitted light; the
  reviewer named the lighting a MAJOR ("a different person", nose / neck cast shadows), which is not a model fault.

## Source-asset scope: LOD and conversion stages are judged against their source (2026-10-16)
Why: the hair-cards gate swung 19-29 game-visible MAJORs over six rounds (g3-g8) because every review mixed two
questions: do the CARDS reproduce the GROOM (the cards stage), and does the groom match the PHOTO (the approved groom's
stage, decided with Joe). Card changes could not move photo-vs faults that the groom itself has (thin cap / open
forehead, narrow silhouette, colour vs the photo, side volume, centre part, face-framing locks), so the count measured
noise between reviews, not the cards.
- A stage that converts an approved asset (hair cards / LODs from a strand groom, a game mesh from a sculpt, baked maps
  from a high poly, a decimated LOD from LOD0) is judged against its SOURCE asset, rendered with the same camera, light
  and head: the blind review takes the source render as the reference, scoped "<this> reproduces this <source>".
- The photo / concept may stay on the sheet as a context column only. A photo-vs fault that the source also shows goes
  to the coordinator's list for the source's stage, never into this stage's count. A fault where the conversion is
  worse than the source and that makes it read further from the photo counts here (it is a cards-vs-groom fault).
- Game-distance rules (above) apply unchanged: 1 m and 3 m, native pixels.

## Reviewer brief (the LOOK step)
Spawn a fresh agent per gate sheet. Give it: the reference crops and result crops as image paths, the stage's
checklist item NAMES (not values), and this instruction: "You are a senior art director. You have no stake in
this work. For each pair, list everything about the result that reads wrong against the reference, worst
first, concretely (where, what, how far off). Don't praise; don't guess at causes. Say if a crop is too small
to judge." It never sees the author's caption or numbers.

## Process rules (2026-10-19, Joe: "are we still learning or thrashing")
- STOP-LOSS: a fault gets at most TWO rounds without a visible change on its own before / after tile. After that, either
  change the METHOD (write it up first) or park the fault with its evidence. No third tweak of the same lever family.
- MEASURE FIRST, AND VALIDATE THE MEASURE: before a measure drives a change, it must reproduce a known-good case (the
  reference against itself, a planted fault found). Today's wasted rounds came from unvalidated measures: uvs read upside
  down, AgX vs PBR Neutral compared, a half-sided preview, a photo mask dropping highlights, judging against the strand
  groom instead of the photo, and swapped reviewer labels.
- PROVE ON THE CHEAP PATH: try a change on a saved dump / a single-part bake in about a minute; full exports only confirm.
- CROPS, NOT SHEETS: agents and reviewers look at single-feature crops at modest size. Full sheets are for Joe only.
- REVIEWS: keep / revert by a side-by-side review in ONE sitting (bin/review-ab); check the key against the descriptions.
  Counts from different reviewers are not comparable.
- STATE pages (docs/state/) are the only required reading; notes are grep-only logs.
- Isolate before tuning (2026-10-19): a visible fault (black specks, a seam, a flap) is first located (which mesh, which
  face, front or back, ray-cast from the pixel) and its cause isolated by one-switch renders (AO off, flat emission,
  culling on/off, one layer alone). Only then a fix. Turning look levers on an unlocated fault is how Garrett's nape
  specks survived three levers that changed nothing (sh5).
- ONE VIEW PER REVIEWER TURN (Joe 2026-10-19): a reviewer (bin/review, review-ab, or a fallback subagent) sees one
  reference | result crop of one region from one camera per turn, never a contact sheet. When the CLI is refused, run
  `bin/review --dry` / `bin/review-ab --dry`: they gate the inputs (reviewgate: captions, sheet size, grid gutters)
  and write the pair images + prompt.md; give the fallback subagent ONE image per message. Sheets are for Joe only.
  Construction reviews pair the clay crop with the diagnostic crop (diag render) of the same view.
- ONE AGENT PER THREAD, SEQUENCED (2026-10-19, clothing): within a thread, one agent at a time; each step lands on
  main before the next starts, so every agent starts from the same state and results stay comparable. Parallel only
  across independent threads, never two agents editing the same module. One ordered plan per thread, each step with
  its question stated up front. (Today ~10 stacked dress-form branches + 5 parallel cloth agents: flag-name
  mismatches, ledger id collisions, a fit validated on the pattern being replaced, sheets nobody could compare.)
