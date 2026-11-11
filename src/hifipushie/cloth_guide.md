**The fit and styling rules (2026-10-25; ledger docs/notes/codified.md):**
- The MUSLIN fit is the fit (C162): woven cloth, threads held, the bias shears up to the weave's jam, a soft neck pin
  (C166, C167). Misfit reads as thread strain by region; cloth never stretches to reach a landmark.
- SUPPORTS, NOT HOLDS (C190): hold only what physically carries the garment (shoulder / neck contact, sewn seams,
  fastened closures, the layer under), soft and named. Holds standing in for gravity made pinches, narrow hems, a
  side seam standing like a cord and rigid-grip creases.
- THREADS FIRST, THEN BENDING (C195): stiffness never buys shape with stretch. Collars and canvassed fronts hold their
  shape by drafted canvas / interfacing (C196); if two goods trade off, the model is wrong.
- Styling (C142, C174, C199): pull until a thread would stretch; a hand lets go after its move and what hangs free
  drops; every styling ends with smooth + pull down.
- Judge beside the REFERENCE only: your current or approved garments are never the baseline (C165). Verdict: overall
  standing first, then faults ranked.

## The stages

## Stage 0: describe the garment (before any template or default)

## Stage 2: measure the draft against the description

## Craft rules (each once; the reasons and numbers are in the sub-topics)

Judging
- Measure what you name, on BOTH sides (a "notch" is the apex where collar end meets lapel, not the collar's tip).
- Front-view widths are what sticks out (shoulder width = the sleeve heads: cap ease, not the block's shoulder).
- Judge clay with shadows off and close cameras for small features; textured looks for seams, plackets, buttons.
- Judge against the reference in ITS pose (raise the arms on a copy if it raises them).
- A tucked under garment is never drawn without the garment over it.
- A render made before a code or pattern change shows the old result: check both renders in a comparison are current.

## Self-review loop (every round, from the form fit on)

A clean result that isn't the reference is wrong: no crossings, no strain and a "fits" verdict say the simulation
worked, not that the garment is the one in the picture. Don't argue a MAJOR away with numbers; argue only with
evidence that the reference doesn't show it.

## Common mistakes

Full fault table with causes and fixes: guide(topic="cloth_faults").

## Known gaps (decide them in the description, don't discover them at the end)

- Fabric surface in the detail maps: `detail.surface` "knit" (stockinette V stitches, rib on the band roles;
  `detail.knit` wale / course / depth / trough) or "twill" / "plain" (a woven cloth: twill ribs only where the atlas
  resolves them, plus the crush, the short creases a worn cotton takes everywhere; `detail.woven` crush (m, 0.0003) /
  crush_size / crush_dir / crush_spread). A woven garment with no surface reads smooth and rubbery at game distance:
  measure fine (3-6 mm) contrast on a flat panel against the reference before tuning `crush`.
- Jeans: arcuate back-pocket stitching, rivets, coin pocket and indigo wear / fades aren't built; garments take one
  colour plus the sewing detail maps.
- A fitted jacket's side-back and underarm seams start far open (one start cylinder at the widest level): read their
  start gaps on every fitted jacket.
- A notched collar's ends where they meet the lapels can crumple; `collar_ends: "draped"` is experimental.
- Worn garments are drafted from a `base` body's measurements: a creature built from blobs has none. It can take a
  flat piece draped over the model (`{"drape": {"over": "model"}}`) or a clothing shell part with fold strokes
  (guide(topic="parts")).
- Welt pockets' cut and bag, a lining with its own pleat, pleats that die inside a piece.

Two solvers: Blender's cloth (the default, local) and ZOZO's contact solver (`"backend": "zozo"`: intersection-free,
strain limited). A ZOZO job runs on this machine's GPU, or through your own remote command
(`$HIFIPUSHIE_ZOZO_REMOTE`, run with the job folder; it must leave out.npz there). Backend `"file"` writes the job
folder and waits for someone to bring back out.npz; backend `"remote"` runs `$HIFIPUSHIE_CLOTH_REMOTE` with the job
folder. Results are keyed on the job, not where it ran. Details and timings: guide(topic="cloth_sim").
