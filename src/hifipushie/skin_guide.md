# Skin: texturing a human the way character artists do

Tools (`enable_toolset("human")`): `skin` (describe the skin), `look_skin` (fast close-ups + measurements),
`skin_from_reference` (measure the skin in the model's fitted reference pictures and set the description from it),
`skin_project` (the pictures projected into the head's atlas as a measurement), `skin_reference` (every key, default
and zone), plus the ordinary paint tools (`edit_model` paint ops address the same anatomy with `{"zone": name}`).
`spec["skin"]` expands into ordinary paint layers `skin:<layer>` laid UNDER the model's own paint, plus the skin
part's shading. It needs a model on a `base` (a MakeHuman or template body; a GNM head for the face's `lm_*`
landmarks).

Sub-topics (guide(topic=...)): `skin_layers` (every stage in detail: the person under the skin, pigment model, zones,
mottling, features, folds, hair on the skin, eyes, micro detail, roughness, cosmetics, shading; what goes wrong;
sources), `skin_tools` (every skin tool's parameters; guide(topic="tool:skin") is the `skin` tool's own section).

**The rule everything else follows: read the skin from the reference before setting anything.** Tone, redness and
where it sits, texture scale, lips, under-eye, brows, creases, eyes: as measured items, each compared close-up beside
the reference crop at the same framing. A skin that measures like "real skin" in general but not like THIS person's is
wrong.

## Why CG skin reads as plastic (measured: photographs vs a flat-colour skin)

| what a photograph has | photographs | one colour + one roughness |
|---|---|---|
| lightness contrast at 0.35-1.4 mm (pores, skin lines, their highlights) | 0.8-1.3 L* | 0.04-0.08 |
| colour (a*) contrast at 1.4-11 mm (mottling, freckles, redness) | 0.4-0.6 | 0.04-0.11 |
| a highlight | 5-13% of a cheek or forehead, broken into 1-10 mm pieces | none |
| cheeks and nose redder than the forehead | a* +1 to +7 | +0.3 |

In order of how much they matter: no fine relief (so no broken-up highlight); one albedo colour (no zones, no
mottling); no visible specular (one high roughness); no red in the shadow edge and no light through thin parts; lips,
brows and eye area painted as flat shapes. `look_skin` prints these numbers for your model next to the photographs'.

## Stage 0: read the reference (before any key)

Per item: the reference's value (measured or read), how you'll measure yours, a tolerance; say which reference is the
authority for colour (the most frontal, evenly lit one) and mark what no picture shows as inferred. With fitted
reference cameras (the block-in's), `skin_from_reference(read_only=True)` measures most of this; read it as data and
check it by eye.

1. **Overall tone**: L*a*b* in named boxes (forehead, cheek, nose, chin). Judge tone on the FOREHEAD (cheeks flush);
   check the photo's cast on the sclera (neutral ~R/B 1.0-1.1) before trusting its numbers.
2. **Redness distribution**: where (cheeks, nose, ears, chin), how broad, how strong against the forehead (a* +1..+7).
3. **Pigment and texture**: freckles (where, density, size, clumping), moles, spots, veins; pore and skin-line scale
   and how visible at the reference's distance; the highlight (how big, how broken up, oily T-zone or matt).
4. **Lips**: colour against the skin, how sharp the vermilion border is, finish (matt, balm, gloss).
5. **Eye area**: under-eye tone (purple-blue, dark circles), lid redness, the upper lid crease (height above the
   lashes, how crisp, hooding), bags; lashes; iris colour, sclera, catchlight.
6. **Brows**: shape, density, length of the tail, colour.
7. **Creases and folds**: nasolabial, marionette, forehead, crow's feet, between the brows: present or not, depth,
   placement. Age they suggest.
8. **Facial hair**: stubble style and density, where it fades, trim lines, grey share.
9. **Cosmetics**: none, natural, everyday, evening; which products are visible.

Then choose the keys from the items: `age` first (it drives wrinkles, spots, veins and dryness), the tone from the
pigment model (never a colour picker), then features, folds, hair, eyes, make-up. Say which item justifies each.

## The stages (large to small; look after each)

| # | Stage | Keys (guide(topic="skin_layers") for each) | Judge in |
|---|---|---|---|
| 0 | The person under the skin | the `human` tool, `base.body` age / sex / bust, `base.head.follow_body` | whole-figure clay |
| 1 | Base tone | `tone` {fitzpatrick or melanin, blood, undertone}, `age` | `look_skin(views=["bust"], flat=True)` |
| 2 | Colour zones | `zones`, `variation` | flat bust |
| 3 | Mottling | `variation`, `sun` | flat bust, cheek |
| 4 | Features | `features` (freckles, moles, spots, veins, flush, tan), `wrinkles`, `scars`, `tattoos` | lit bust, close-ups |
| 4b | Folds | `folds` (tear_trough, nasolabial, lid_fold, marionette, glabella...): geometry | close-ups under two lights |
| 5 | Hair on the skin, eyes | `hair` (brows, lashes, stubble, scalp), `eyes` | brow / eye / jaw close-ups |
| 6 | Micro detail | `detail` (tiling pores and lines) | `views=["cheek"]` |
| 7 | Roughness, highlight | `oil`, roughness zones | lit close-ups: highlight breakup |
| 8 | Cosmetics | `makeup` | close-ups |
| 9 | Shading check | `shading` (subsurface) | EEVEE `views=["face", "ear"]`, then the exported GLB in EEVEE set up like a game |

From pictures: `skin_from_reference` reads the pictures as a MEASUREMENT (de-lit against your own render under each
picture's fitted light) and sets tone, zones, features, brows, stubble, eyes and folds from them, in rounds;
`skin_project` projects the pictures into the head's atlas as a layer stack. The photo's pixels don't ship; the
decomposition does. Shape first: forms the head should have (a lid fold, bags) go into the head before the projection,
or their shading is taken as pigment.

## Craft rules (each once)

- Skin can't make a face young, old, male or female on its own: proportion and the head's shape do
  (`base.head.follow_body`). Set the person under the skin first.
- Skin colour is two pigments (melanin, haemoglobin): every layer is "this skin with more or less melanin or blood",
  so it comes out right on any tone. A rosy fair face is more `blood`, not a negative undertone.
- Albedo stays inside what engines expect of non-metals (sRGB ~50-240): don't push it darker for contrast.
- Keep zones and mottling subtle: visible as shapes at bust distance is too much (photographs: cheeks +1..+7 a*).
- Wrinkles and folds are relief + a darker tint + rougher, never painted grey lines; deep folds are geometry.
- Brows are hairs with direction, not a painted arc; real beards have no edge unless trimmed.
- Tattoos are multiplied into the skin under its relief, never a sticker on top.
- Pores are a tiling detail map; at bust distance they should only break the highlight up.
- Never one flat roughness: the T-zone smoother and oilier with a second tighter lobe.
- Every cosmetic changes roughness and specular, not only colour; pores stay on top of it.
- Too much scattering reads as wax; the shadow edge turns redder, not grey; ears glow back-lit.
- Judge in EEVEE, and the export as the GLB re-imported into Blender EEVEE set up like a game (no ray tracing):
  never in Cycles.

## Self-review loop (every round)

1. Render close-ups per feature (`look_skin` views: bust, face, cheek, eye, brow, lips, ear, jaw; flat and lit) at the
   reference crop's framing, and put each BESIDE the reference crop. A whole-face sheet is not enough: skin is judged
   feature by feature.
2. Per region (tone, redness, texture and highlight, lips, under-eye and lids, brows, creases, facial hair, eyes),
   list what reads wrong against the reference, concretely (where, what, how far off). Mark each MAJOR (wrong tone or
   redness distribution, plastic or waxy, a missing or extra feature that identifies the person, painted-on shapes, a
   visible defect) or MINOR. Order: form (folds, creases, relief) before colour layers, colour before fine texture.
3. Fix the worst MAJOR at its stage; re-render; re-measure the stage 0 items (table: item | reference | ours | pass).
4. Repeat until no region has a MAJOR.

`look_skin` numbers saying "like real skin" are necessary, never sufficient: the skin must read as the person in the
reference. Argue a MAJOR away only with evidence that the reference doesn't show it (a crop too small, a lighting cast).

## Common mistakes

| Mistake | Instead |
|---|---|
| Starting from a default tone and adjusting by eye | Read tone from the forehead box of the authority picture; set it through the pigment model |
| Judging the whole face at bust distance only | Close-ups per feature beside the reference crops |
| Recolouring lips or palms by hand | `lips.blood` / `lips.melanin`; zones handle palms |
| Freckles like a rash | Lower `amount` before `size`; real ones cluster and vary |
| Wrinkles on a 25-year-old, an 80-year-old without crepe | Set `age` first; `wrinkles.amount` |
| A crease or bag painted on | `folds` (geometry) with their tint |
| A tattoo that looks printed | `tattoos` (multiplied, aged), not a paint layer on top |
| Make-up that looks like paint | Check its finish; foundation still carries some `variation` |
| A shading shadow in the photo taken as pigment | Put the form in the head first (lid fold, bags), then read / project |
| Judging skin in a path tracer (Cycles) | Judge in EEVEE and on the exported GLB in EEVEE set up like a game: that is what ships |
