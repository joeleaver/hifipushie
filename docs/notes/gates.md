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

## Reviewer brief (the LOOK step)
Spawn a fresh agent per gate sheet. Give it: the reference crops and result crops as image paths, the stage's
checklist item NAMES (not values), and this instruction: "You are a senior art director. You have no stake in
this work. For each pair, list everything about the result that reads wrong against the reference, worst
first, concretely (where, what, how far off). Don't praise; don't guess at causes. Say if a crop is too small
to judge." It never sees the author's caption or numbers.
