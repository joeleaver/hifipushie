# Hair

Hair is not part of the SDF field: it lives in the model's Blender scene, so hair edits never rebuild the body. Three
paths, pick by the job:
- REALISTIC hair (the default for a realistic human): a STRAND groom on Blender's Hair Curves (`hair.style`
  "strands"). Tied back (ponytail, bun, plait, half up): `tie_hair` with a few style words (below). Loose: `groom_hair`
  with `groom.loose`. Short cuts: a baked cap + sparse cards (below). Judge in EEVEE (`look_hair`).
- STYLISED, feature-animation hair: sculpted LOCKS (a few big designed shapes): guide(topic="hair_locks").
- GAME export: cards cut from the strands (`export_hair` / `export_asset`).
Why the tools are built this way (practice, sources, engines, what went wrong): guide(topic="hair_background").

## Two principles (Joe, hair-heads) that every groom keeps
1. **Hair is distributed EVENLY over the growing area; parts are from styling, not distribution.** Roots come from one
   even sampling of the hair-bearing scalp (inside the hairline, its only ramp the hairline's own edge); a part, a sweep,
   a whorl is the COMB DIRECTION of strands from roots on both sides, never an absence of roots. Locks / clumps steer
   direction. Knob: `strands.even` 1 (the reader's default for loose long hair): EVERY strand is a child
   interpolated at its even root from the nearest lock GUIDES (the locks are guides, not root owners: march them dense,
   `groom.loose.spacing` 0.004), each bank of the part its own object (the left / right guides only; Blender's "Part by
   Mesh Islands" alone still averaged guides across the part: children on the line fell down the forehead as a veil).
   The guide field must be SMOOTH: a child averages ~3 guides, so a guide combed the other way among its neighbours
   (`part_soft.cross`) makes children down the middle (keep cross 0 with even 1), and guide wave phases come from a
   smooth field of the root (random phases cancelled into straight hair). Interpolated children get Blender's Clump.
   Below 1, `even` is a share: a cover layer trimmed to 7 cm under the lock strands (the older workaround).
   Measure: the MAGENTA COVERAGE check (spikes/hair_garrett/hcover.py: the scalp painted magenta, the share of it
   showing inside the hair region from above / behind / 3-4; target ~0 outside the part line). A GATE: no head ships
   with magenta OFF the part line from above (t60; a clean part line alone is ~1.2 % on a long head) or any from
   behind; run it beside the regression sheet. hcover finds magenta by hue (seen through dark hair it is dim purple).
2. **Hair ARCS UP from the scalp, then falls; flat-from-the-root is a style choice (slicked, wet, tight), never the
   default.** Every strand leaves the scalp at an angle, rises by its root lift + the hair under it, turns and falls;
   the top's volume comes from that arc and it also covers the scalp. Knob (loose hair): `groom.loose.lift` from the
   measured stand-off (~1-1.5 cm on long hair), `out` 0.2-0.25 on the front / top, `stiff` ~0.35; tied hair: `volume`
   (rules 1-2). The reader's loose start sets `out` by region from the measured stand-off (0.25 x mm / 10 on top).

## Step 0: DESCRIBE THE STYLE IN WORDS from every photo before grooming (hair-heads; Joe on three heads: "a completely different hairstyle")
Before any knob, write down from the front, three-quarter and profile pictures, then the same for OUR render, then the
differences; rebuild the groom from the description (hairline curve, part, comb direction and lift by region, edge
density), never by tuning the last groom. Numbers (the reader) do not see a style: a short cut combed ACROSS read
"brushed up and back" by every measure while the render was a different haircut. Say:
- the hairline: its curve, how far the temples recede, where the front edge sits against the brows (in cm), whether the
  visible edge is the hairline or hair lying over it, how thin the very front is, whether skin shows through;
- the part: where, how deep, how much scalp shows (or none);
- which way the hair is combed and lifted by region (front, top, sides, back) as SEEN in each view: up / back / across /
  forward, lying flat or standing, and how far the front stands off at the forelock in profile;
- long hair: how it leaves the part and falls, volume at the crown, how it frames the face, what is tucked / swept /
  in front of the shoulders, the length and how the ends sit, the wave pattern by region.
Then groom from those sentences, one region at a time, and judge the region against its sentence.
Learned on the man's short cut: the front read "up and back" from the reader's sweep; in words it is combed ACROSS to
one side, lying low, the edge lower and rounder than the bare hairline: `flow.front` across (x), `lay` 0.6, roots ON the
line (`loose.inset` 0.0005: 4 mm in, the strip in front of the roots was dark scalp-tinted skin under a wall of hair)
and the hairline's front points ~1 cm lower where hair lies over the forehead.

## What makes hair read as hair (the checklist; tesshair7, from seven rounds of Tess's ponytail beside her photos)
Judge each, one area at a time, against the reference in the same camera (`look_hair(views=["ref0", ...])` or
fitted-camera close-ups); fix in this order. A rule's MEASURE is how to check it, its KNOB what sets it.

| # | rule | the fault when it is missing | measure | knob |
|---|---|---|---|---|
| 1 | The mass stands OFF the skull: real hair is ~1.5-2 cm off the skull over the top and sides, 3-4 cm above a low tie | a combed cap hugging the skull ("flat") | outline stand-off from the skull through the fitted camera (spikes/tesshair7/standoff.py; mm per direction); in a ROOM (a couch, a shirt) the stand-off only counts where hair meets the backdrop: measure the outline by HEIGHT from the parser instead (spikes/hair_garrett/widths.py: width per cm in front, reach behind the skull in profile) | `volume` (amount, crown / sides / nape, hold); loose long hair: `groom.loose.body` (the lengths fill out as locks come down: 8 -> 25 mm took a lank head to her mass), waves in the lengths (`wave_from`) |
| 2 | From the parting the hair RISES and arcs over, then falls down the side: convex arcs, not straight lines to the tie | straight diagonal strands laid flat | strand paths from the part drawn on both pictures (flowlines.py); the lock plot (lockplot.py) | `volume.root` (bend radius), `volume.arc` |
| 3 | The mass is LOCKS with depth, not one shell: under-layers darker, locks of different height and width | a smooth helmet | by eye in close-ups; colour_variation `mass_sd` | `volume.layers`, `volume.locks` (keep <= 0.4: at 1 the crown's silhouette is wavy wires), look `depth` |
| 4 | A HALO: fine, light, slightly curly hairs standing a few mm off the top layer along the whole silhouette | a surface, not hair (the strongest single tell) | by eye at the silhouette in front / profile; hair_from_reference: halo density, wisps / 10 cm (compare= ours vs picture) | `wisps.halo` (default with volume; gentle curls, never the old `strands.halo` on every lock: a wire grid); LOOSE hair: `groom.loose.halo` / `flyaway` (its free locks were quartered like a tail: two long heads read a third of their pictures. halo; hair-garrett) |
| 5 | The PARTING is a soft line: hair rises and falls both ways, crosses it, scalp barely shows; it fades out a few cm back | a clean notch between two lobes, dark roots | close-up of the part from the front | `hairline` (zig), `volume.cross`, halo crossing (28 % of `wisps.halo`), part rows drawn fine |
| 6 | The HAIRLINE thins out over ~1 cm with fine baby hairs; the temple is hair down to the ear | a hard dark edge, a shaved temple, a grey veil | close-ups of both temples and the forehead's corners | `hairline`, `wisps.baby`; the ear is found on the mesh (hair.ear) |
| 7 | WISPS / escaped strands are fine, near-straight with a soft bend, a little lighter, hanging close to the face | corkscrew ringlets (doll-like), black wires, a grey veil of flat clumps | close-ups of the temples and in front of the ears | `wisps.curls` (escaped strands), `wisps.amount`; flat clumps are cut back automatically under volume |
| 8 | COLOUR varies like real hair: per-strand and per-ribbon variation, darker roots, lighter older lengths, light ribbons ~10 % of the hair | "one flat brown" | `hair.colour_variation` (look_hair measure colour): hers on Tess L_sd 7.5, strand_sd 4.2, ribbon_sd 3.0, light ribbons 9-10 % at + 5.7 L* | look `variation`, `vary`, `highlights` + `highlight_contrast`, `root_dark`, `sun` |
| 9 | LIGHTENING is lighter AND warmer, never greyer; the overall colour by measure (chroma, hue) | ashy grey lengths; ginger when overshot | colour_bands chroma / hue against the picture (Tess: chroma 8-9, hue ~69) | look `lit`, `gap`, `eevee_sat` (Tess 0.38), `sun` |
| 10 | Highlight RIBBONS are irregular: a few broad soft ones and many thin, fading along their length, on the top layers | regular pinstripes; flat tan painted bands | colour_variation `ribbons.share` / `contrast`; by eye | look `highlights` (two scales built in) |
| 11 | A light catches the hair: a sharp pale lobe toward the root and a broad warm lobe toward the tip (Kajiya-Kay / Marschner R and TRT) | matt, grey, plastic | a lit close-up of the dome beside the photo | look `gloss` (EEVEE; 0.6 on Tess). Cards: the card material's anisotropic two-lobe specular along the tangent (the cards carry tangents) |
| 11b | Thin hair GLOWS: tips and fine / single hairs lighter and warmer (light through them), and see-through toward the tip | an opaque cut-out silhouette, solid tips | colour_variation `edge_L` vs `core_L` (Tess: the outline's thin hair ~2-5 L* lighter than the mass) | look `backscatter` (a translucent, back-lit warm term weighted to thin hair), `tip_alpha` (dithered alpha over the last 30 % of a strand). Cards: the atlas already fades its tips' alpha; back-scatter is the card material's transmission / subsurface term (UE groom: dual-scattering; a card shader: a back-lit wrap term) |
| 11c | The CORE of the mass is darker and richer than its outer layers (multiple scattering inside a mass) | one flat value through the mass | colour_variation `core_L`, `core_chroma` | look `scatter` (by a lock's depth hp_sh: darker, more saturated) with `depth`. Cards: the cards' vertex colour carries depth (lower layers darker); saturation is a card-material tint |
| 12 | A TAIL is strands from behind, not wide ribbons: finer strands, locks a little out of step, a ragged soft end | wavy ropes / ribbons, straw | back three-quarter beside the photo; tail area / length / width by mask (look_hair measure) | `tail.wave` (Tess 0.35), `tail.fullness`, `tail.tousle` |
| 13 | Up-styles (high ponytail, top knot, man bun) and half up have NO volume by default: hair pulled up does not fall from its roots | radial ridges round the hairline, specks at the crown | the riffs sheet | volume is gated by tie height and half up; asked for there it is a smooth pouf |
| 14 | A SHORT CUT has LENGTH AND LAY BY REGION: longer on top and front (4-6 cm), clipped sides and back (1-2 cm), a taper to the nape (~0.5 cm, a soft edge); combed ONE way per region; fine, straight, dense strands (hair-garrett) | long-hair machinery on a crop: wavy clumped noodles, wings at the sides, a curly astrakhan back (laid locks thicker than twice their clearance sink half their strands into the skin and crumple when pushed out) | `hair_from_reference` stand-off by region ours vs picture (`compare=`); the back and nape close-ups; the lock plot | `groom.loose` length / lay / flow / lift (per region), `thickness` <= 3 mm; strands: count 200k+, thickness ~0.9, clump ~0.1, wave / curl / loose 0 (the reader's start sets these) |
| 15 | FINE strands at the picture's scale: short hair at bust distance is a near-continuous fine texture; strand-to-strand contrast as the picture's | wires, straw, a hairline of comb teeth (each lock's strands start as one blunt row) | `hair_from_reference(compare=)` colour variation `strand_sd` ours vs picture (hair-garrett r4: 9.3 vs 6.8: too coarse) and hairline softness (1.0 vs 3.5 mm) | strands `thickness` / `count` / `clump`, `fly_light` lower on grey hair, the hairline's density ramp (`soft`, `baby`): NOT yet enough on a crop (hair-garrett). DENSITY that reads as one combed surface is the LOCKS' coverage, not the strand count: `groom.loose` spacing 5 mm, width 2.4, body 4 mm (+ count 600k) closed the scalp-between-ridges look on a crop; count, thickness, clump and stray alone barely moved it (hair-heads r11, isolated one at a time) |
JUDGING RENDERS AT A PICTURE'S SCALE SUPERSAMPLE: EEVEE draws every strand at least one pixel wide, so at a photo's
own scale (~0.3 mm a pixel for a head-and-shoulders picture) a 0.05 mm hair is drawn as a 0.3 mm wire: the hair reads
coarse and wiry whatever the strand dials say. Render 2x and average down (hair-garrett hgshots `ss=2`) with more
strands (count ~300k on a short cut) before judging rules 3, 8 and 15 against a photo; coverage drops, so redo the
colour step afterwards (mean L* fell ~6 on the man's crop). A game gets the same from TAA / alpha-to-coverage on thin
cards, not from thicker strands.
Before a change ships: re-render the accepted styles and riffs beside their last accepted renders (the regression
sheet: `run.sh regress.py run tag=X` then `regress.py sheet tag=X`, spikes/tesshair7/regress.py + accepted.json:
Tess's best through her fitted cameras + ten riffs on two other heads, each ACCEPTED | NOW | difference; renders are
deterministic, so any mean difference over 0.3 flags MOVED; `regress.py accept tag=X` after a human look) so a fix
can't silently break what worked.
Isolate a fault before fixing it: render the groom with one piece off at a time (shots7.py `drop=<lock pattern>`,
`S=<strand dials>`, `LS=<pattern>:<dials>`, `look=@file`): the crown's wire grid was the halo dial, the grey veil the
flat wisp clumps, the dark tangle at the part's start the far bank's strands seen end-on.

## The look: colour keys for strand hair (`look` in tie_hair / groom_hair)
| key | what it does |
|---|---|
| gap, lit | the dark-to-lit range |
| root, edge | how far root and edges darken |
| vary | value per lock |
| tip, tip_amount | tips lighter or warmer |
| variation | 0..1 (strands; default 0.4): natural hair is never one colour. Locks drift in lightness, sub clumps and strands in hue and saturation. 0 = one flat colour (with `vary` 0) |
| sun | 0..1 (strands; default 0.2): SUN-LIGHTENED lengths. The hair lightens and warms with its AGE, metres from the scalp (full by 28 cm): roots stay the look's colour, a ponytail's ends are the lightest. A tail's hair counts from where the gathered hair ended, not from a new root |
| highlights, highlight_contrast | 0..1 (strands; default 0): lighter, warmer RIBBONS at two scales (many thin ~4 mm, a few broad soft ~15 mm, irregular edges), starting a few cm off the root, coming and going along their length, gathered where the sun reaches (the top layers, round the face, a tail's outside) and a little on some locks; contrast 0..1.5 (default 0.6) |
| root_dark | 0..1 (default 0.5): how dark the root's first stretch (`root` of the length) is; 1 = the gap colour. A tail's strands have no dark root |
| gloss | 0..1 (EEVEE strands; default 0): the highlight where light catches the hair, as two lobes: a sharp pale one shifted toward the root and a broader one in the hair's own warm colour shifted toward the tip |
| fly_light | 0..1 (strands; default 0.3): hairs that left the mass (fly-aways, the halo, wisps) read lighter |
| depth | 0..1 (strands; default 0.5): the under-layers of hair with `volume` are darker (the shadow EEVEE's strands do not cast on each other) |
| vary | the value noise per strand / sub clump under all of it |
| sun_warm | 0..1 (default 1): how much the sun-lightened lengths also warm; 0 = ASH lengths (lighter, a little less saturated: a mousy / ash brown) |
| seen as floats | `look.seen` may be [r, g, b] sRGB 0..1: near-grey hair's hue does not survive 8 bits (one hex digit = 5-10 deg at chroma ~5); the reader's colour step emits floats |
| sun_length | m (default 0.28): the hair's age from the scalp by which `sun` lightening is full. The FRONT view sees the first 2-10 cm of every strand, the back the lengths: at 0.28 the dome stays dark from the front while the back is light; Tess 0.06 (with root 0.05: a little root darkness at the part) |
| tip_alpha, backscatter, scatter | 0..1 each (EEVEE strands; default 0 = off): the game hair shader's terms: see-through tips, warm light through thin / back-lit hair, a darker richer core with lighter outer layers (Tess: 0.5 / 0.6 / 0.8; checklist 11b, 11c) |
Also: eevee_sat / eevee_gain (how EEVEE draws the colour; Tess 0.3 / 1.4), seen (the colour it should READ, e.g. from a
photo), grey_amount, cycles_* (Cycles only). Match by measure: look_hair measure "colour" (colour_bands + variation).

## The stages

1. **Groom the shapes** as for any hair: hairline, parting; LOOSE hair with `groom.loose` (below); tied hair with
   `groom.tie` (`{"at": [176, 30], "out": 0.03, "gather": {rows, locks, lift, width}, "tail": {length, fullness,
   locks}, "escape": 6}` + `parting.side: "none"`). Judge the silhouette first (`stage: "mass"`).
2. **Turn on strands and set the character of the hair** with `strands` (all 0..1 dials unless a unit is given; they
   cannot reach values that stop reading as hair):

   | dial | what it does | when wrong |
   |---|---|---|
   | count | strands in a look (30k default; 60-100k for a Cycles beauty) | too few: see-through in Cycles |
   | clump, clump_size (m), clump_shape | strands gather into sub clumps; where along the strand | 1 / shape 0: ropes |
   | stray | share of strands that only half join their clump | 0: each clump a rope with air between (pasta) |
   | wave (m), wavelength (m), curl, random | the lock's swing; `random` = how far sub clumps fall out of step | random 1 on a tail: pasta |
   | loose, frizz, flyaway | strands wandering together / singly / letting go | frizz high: a cloud |
   | tips, roots, taper | ragged ends, staggered roots, strands thinning to a point | tips 0: a cut brush |
   | under, under_length (m), soft (m), baby | the scalp layer and the hairline's fade | under 0: skin through the hair |
   | halo | short broken hairs standing up off the hair and curling (the fuzz round a loose updo against the light); flyaway strands only drift mm off their lock and end where it ends, so flyaway alone shows no halo | 1: a bristly brush; 0.5 a soft fuzz |
   | halo_soft | 0..1: the halo DENSE AND SOFT: up to 4x the halo hairs, ~4 mm off the hair and ~2 cm long (a fuzz along the silhouette, not a few hairs standing off); pair with look `fine_alpha` 0.2-0.3. Matched a grey crop's halo; not enough on long dark hair (hair-garrett3) | 0: the old single halo hairs |
   | free: {dial: value} | the dials of hair that has LEFT the head (a tail) where they differ: a tousled top (loose 0.7) with a tail of defined wavy locks (free loose 0.2-0.35) | loose 0.7 on a tail: crimped wool |
   | on one lock: strands {clump, tips, roots, density} | that lock's own share of the object's dial | |

   A thin lock (< 16 mm) is a wisp: it swings less and slower by itself (at a lock's wave a few hairs side by side
   read as crimped ramen). Hair gathered into a tie narrows into it and every strand reaches it.
3. **Look**: `look_hair` renders the strands in EEVEE in seconds under a key, a fill and a rim light (`look.light`
   "salon"; "flat" = one sun). `engine="cycles"` path-traces them with the hair BSDF: the truthful look (1-4 min; it
   waits for the machine's heavy slot). EEVEE draws every strand at least a pixel wide, Cycles at its true width:
   a groom that looks full in EEVEE and thin in Cycles needs more `count`, not more thickness.
   **Colour from a photo: `look.seen`**, not `lit`. The colour keys are asked for the renderer, which gives back
   about a third of their saturation (Cycles' hair BSDF; EEVEE's strands copy that), so a photo's light brown typed
   into `lit` renders grey-blond. `seen` = the colour the hair should READ (the median of the photo's LIT hair, not
   its shadow side: the render makes its own shadows) derives lit / gap / sheen / tip / eevee_sat / the scalp tint
   (EEVEE then draws seen exactly; Cycles as much as the gamut allows). Colour keys given beside it still win.
   Measured once (jw, flat frontal light): the rendered lit hair came out ~1.25x as saturated as seen: ask a little
   less. Hair against a warm wall in the photo looks ashier than the same numbers on our grey backdrop.
4. **Export for a game**: `export_hair(name, out_dir, tiers=["hero", "main", "npc", "far"], save="sheet.png")`.
   Cards are CUT FROM THE STRANDS: the strands of a lock are clustered (hero: the groom's sub clumps; main: pairs;
   npc: whole locks; far: only hair off the head) and each card's centre line is the mean of its clump's strands,
   its width their spread, so cards wave, part and end where the hair does, and a lower tier has fewer, WIDER cards,
   not the same cards thinned out. Under them: the cap (the scalp's own chart, hairline painted in) and, in a tied
   tail, a solid core shaped by the tail's strands. Under a budget, fly-aways and baby hairs go first and coverage
   last. The groom itself goes out as Alembic (cm, Unreal) and USD (groom_* primvars).
5. **Judge the export as an engine draws it.** The sheet shows the strands, then every tier's GLB re-imported on
   the head under a hard alpha TEST and dithered, then the cards as solid quads by layer. The table per tier and
   view: `iou` / `bare` (strand silhouette the tier leaves uncovered), `value` and `sat` x the strands', `stamps`
   (detached rectangular blobs: a card's quad showing), `straight` (outline made of plank edges), plus WARNINGs for
   card vertices under the skin and wisps whose root lies on bare skin. To find what makes a fault, `look_hair(tier=
   "hero", debug=...)`: "layers" (solid quads by layer), "cap_only", "cards_only", "no_normal", "unlit". If a
   pattern survives "unlit" it is in the colour (atlas or vertex colour); if it survives "no_normal" but not
   "unlit" it is the cards' geometry and shading.

## Tied-back hair as a STYLE: `tie_hair` (ponytail, bun, plait, half up)

The way to ask for swept-back tied hair. One call, a handful of words; the same call on any head gives the same
hairstyle, and a riff changes one word:

```
tie_hair(name, style={"tie": "low", "side": "left", "tightness": 0.3, "neatness": 0.2,
                      "tail": {"length": 0.24, "wave": 0.8, "fullness": 0.8}})     # a loose low side ponytail
tie_hair(name, style={"tie": "high", "side": "centre", "tightness": 0.9, "part": "none"})   # riff: high and tight
tie_hair(name, style={"tail": "bun", "tie": "top"})                                # riff: a top knot
tie_hair(name, style={"tie": "low", "side": "left", "tightness": 0.85, "neatness": 0.95, "wisps": 0.7,
                      "tail": {"length": 0.24, "wave": 0.6, "fullness": 0.75}})    # sleek head, front wisps, a poofed tail
tie_hair(name, style={"hairline": 0.0})                                            # riff: a gelled, hard-edged hairline
tie_hair(name, style={"tail": {"tousle": 0.9}})                                    # riff: a messier tail (ragged end, strays)
tie_hair(name, style={"front": {"looseness": 0.6, "drape": 0.6}})                  # riff: a held-back head with a LOOSE front
tie_hair(name, style={"volume": 0.6})                                              # riff: BODY: the hair stands up from the part and arcs over
tie_hair(name, look={"sun": 0.8, "highlights": 0.4})                               # riff: sun-lightened lengths, lighter ribbons
tie_hair(other, carry_from=name)                                                   # the same hair on another head
look_hair(name, views=["around"])                                                  # six sides with the bust
```

What the words mean (all optional; `tie_hair(name)` alone is an ordinary low ponytail with a centre part):

| word | values | what it does |
|---|---|---|
| `tie` | nape, low, mid, high, top (or deg) | the tie's height on the back of the head |
| `side` | centre, left, right (or deg) | off to the person's own left / right (a side ponytail) |
| `tightness` | 0..1 | 1 = scraped back flat; 0 = loose: the hair sags between root and tie, stands off the head, hangs over the temples |
| `lift` | 0..1 | a few mm of lift at the roots and over the top (default 1 - tightness); the default of `volume` |
| `volume` | 0..1, or {amount 0..1, crown, sides, nape (x the amount there), root 0..1, arc 0..1, layers 0..1, hold 0..1} | the hair's BODY over the head. 0 = a cap lying on the skull (every strand runs straight to the tie along the scalp); 1 = big loose hair. With volume the hair STANDS UP out of its root, and out of the parting on both banks (`root`: 0 = eases off the scalp over ~4 cm, 1 = stands straight up and bends over within a cm), carries a dome (3.4 cm at the crown, 3 cm above the temples, 1.4 cm at the nape at amount 1; widest high, close where it passes over the ear), in LAYERS (`layers`: 0 = one shell, 1 = locks at every height: a thick mass, under-layers darker by look.depth), and its way first FALLS sideways and down from the root before the tie takes it back (`arc`: convex arcs from the part to the temple; default = amount), keeping its height until just before the tie (`hold`, default 1 - tightness; the tie then stands further off the head). Also `locks` 0..1 (the mass as LOCKS, not one combed shell: each lock's height swells and sinks along it, it wanders and crosses its neighbours, a few are lifted off the mass, widths and clump sizes differ; default by the amount) and `cross` 0..1 (a share of a part's bank locks lean over the line: no clean valley between two lobes). Default: `lift`, but NONE for an up-style (tie high / top: hair pulled up does not fall from its roots; asked for there it is a smooth pouf without fall, layers or locks) and none for half up. Measured on Tess's pictures: her outline stands 17-19 mm off the skull over the top, 17-24 mm at the sides, 30+ mm above the tie; that is amount 0.5 (crown 0.75, sides 0.6, hold 1) |
| `part` | centre, left, right, none | none = combed straight back; a part is combed away from on both banks, in front only |
| `ears` | tucked, covered | the hair passes over the ears' tops, or hangs over them |
| `tail` | {kind: tail / bun / plait / none, length m, fullness 0..1, wave 0..1, tousle 0..1, to: back / shoulder} | what leaves the tie; a tail HANGS (gravity, the neck and shoulders hold it). `fullness` is its VOLUME: 0 = a sleek thin tail (1.8 cm radius), 1 = bushy (6 cm, more locks, airier, frizzier); it opens out of the band as a fan, full by ~9 cm. `wave`: 0 = straight, 1 = loose waves that run through the bundle (neighbouring locks nearly in step: sheets, not ropes). `tousle`: 0 = brushed (an even end, nothing leaves the outline), 1 = tousled, as SOFT irregular hair: some locks loosened out of the bundle, lock ends anywhere over the last half and open (no points, no flick), strands drawn fine at up to 2.7 x the count, single hairs and a few thin locks up to 18 cm leaving the outline with a curl; default 0.05 + 0.75 x wave. The hang, fullness and wave are the brushed tail's |
| `wisps` | 0..1, or {amount 0..1, where: [part, front, temple, sideburn, nape], length [m, m], softness 0..1, loose: n, curls: n} (`curls`: fine separate CURLED locks a side, 5-12 hairs each, that leave the hair at the forehead's corners, the temples and in front of the ears and hang close to the face, each with its own length and helix; default round(9 x amount). Under hair with `volume` the flat clumps are cut back: lying on the skin they show as a grey veil) | the short soft hair that never reached the tie: small clumps of fine hairs along the hairline that fall along the skin (the front's out toward the temples; the temples' are a short fringe in front of the ear, about half drawn back toward the tie). softness 0 = small defined locks, 1 = wide and frizzy. `loose`: THICK loose locks a side (18-45 hairs, 9-19 cm) out of the forehead's corner and the temple, swept back over the temple toward the ear and drooping; default round(2.5 x amount). Default amount from neatness (none on a neat head); independent of it when given: a sleek head WITH wisps is `neatness` 0.95 + `wisps` 0.7 |
| `front` | 0..1, or {looseness 0..1, drape 0..1, locks: n a side} | the FRONT on its own: the hair in front of the ears sags and stands off the head as if the style were that much looser there, while the back stays as tight as `tightness` (`looseness`); it may hang further over the forehead's corners and temples (`drape`); `locks` = thick loosened locks (30-70 hairs) that fall from beside the part across the forehead's corner and are drawn back over the temple (default round(3 x looseness); none toward a tie above 30 deg). Front wisps get thicker, longer and more with it, so they read against skin from the front. Default none: a neat held-back arc |
| `hairline` | 0..1 | how SOFT the hair's edge is. 0 = a clean hard line (gelled; a wig's edge); 1 = the hair thins out over the last centimetre before the line, fine baby hairs (1-4 cm) stand along it from the part to the sideburn, the part wanders a few mm. Default 0.8 - 0.3 x neatness: every real hairline is soft, so this is on for every style (a neat head has baby hairs too) |
| `escaped` | n a side, or {count, where: [part, temple, ear, nape], length [m, m]} | single stray HAIRS (each a thin line: use `wisps` for anything soft); default none |
| `neatness` | 0..1 | 0 = slept in (strays, halo, uneven lengths), 1 = every hair in place |
| `half` | true + `length` m | half up: only the top is tied, the rest hangs loose |
| `detail` | {"tie": {...}, "strands": {...}} | the escape hatch: hair_tied's own keys over what the style makes |

How it is built (hair_flow.py), so you can predict it: roots all over the scalp (not rows from the hairline), each
traced along the head toward the tie: toward the tie + away from the parting + down the head by looseness, never
across bare skin. Hair rooted further from the tie lies over hair rooted nearer. The tail is a bundle of locks that
each leave the tie in a cone and fall; the bundle's radius is then SET along it (the bulge out of the band, full to
near the end), every lock waves on its own phase and plane, turns on its way and ends at its own length, and its
strands end over its last third (thin tapering locks were strings, all strands to the end planks). A wisp is ONE
lock of 6-28 fine hairs (their own part-transparent strand object): its line starts in the hair at the hairline and
is traced along the SKIN (gravity in the surface's tangent plane + a slow curl; it may not lift off while the skin
is under it), its hairs fan a little and end one by one. Escaped pieces are a few single hairs from one root, each
falling on its own.

The hair's EDGE (`hairline`, gather.edge): between the hairline and where the inner roots begin (1.2 cm in) lies a BAND
of fine blue-noise roots. Their locks are narrow, and the nearer the line a lock roots the fewer strands it carries and
the finer they are drawn (part transparent in EEVEE, which never draws a strand under a pixel wide), with soft sides
(`rim`): a density ramp, not a row of full locks starting on a line (that row was the hard dark arc, and where the hair
runs ALONG the line, beside the part and at the temples, its lock starts and sides were stair steps and a V notch).
Inner locks rooted within ~3 cm of the hairline are narrower with soft sides and staggered starts. At the temples and
sideburns the band IS the hair (a strip 1-2.5 cm wide in front of the ear): it is full by 5 mm there and carries more
strands; left unrooted (round four) the temple read as shaved skin. Only the sideburn's lowest fringe, which could
never reach a tie, grows no lock: baby hairs and wisps are that hair. With `hairline` 0 it is the old single row and
the sideburn grows no lock at all.

Cycles (look_hair(engine="cycles")): two look keys calibrate it against a reference, by measure (colour of the dense
hair's shadow / mid / highlight bands through the fitted camera under the fitted light, spikes/tesshair5/cyccal.py):
`look.cycles_width` (x strand width for path-traced renders only: a 70k-strand groom at true hair width is a
see-through veil over the scalp; Tess 1.8) and `look.cycles_sat` (the look colour's saturation kept: dense dark hair
comes out redder than asked; Tess 0.65). EEVEE is untouched by both.

Judge it from every side (`views=["around"]`), not the front: tied hair is wrong from behind first. What to read:
on top the strands must run front-to-back (lateral bands = a cap); the tail must end hanging, not pointing; the
hairline at the temples should be soft (a hard saw edge reads as a wig). The hairline finds the EAR on the head
itself (hair.ear: the bump on the scalp's rays, every base) and passes `groom.hairline.ear` m (default 6 mm) over its
top, with the sideburn `sideburns` m (default 14 mm) below that top in front of the ear: no per-model patch for a
"shaved" temple any more (until tesshair6 the ear was guessed from the brow, 1-3 cm too high; a negative `ear` from
those days is raised to 3 mm over the ear; `"ear_from": "brow"` keeps an old groom's line exactly). On an up-style
(high ponytail, top knot) the hair runs straight off the temple's line: its row of roots stands at uneven depths and
its strands start one by one over the band, so the edge is combed, not a row of teeth; it is still a visible combed
edge close up. Judge a tail against a picture by MEASURE and over seeds: `look_hair(name, views=["ref2"],
measure={"view": "ref2", "mask": hair_mask.png, "tie": [x, y]})` (below), with `groom_hair(name, groom={"seed": n},
replace=True)` for 3-4 seeds: one draw moves a tail's area about +-10 %. What is still weak (2026-10-12): the head
hair reads smoother than loose real hair in EEVEE; a tousled tail is stringier than real brushed-out hair (strands
drawn a pixel wide with dark air between them) and its strays are few; single escaped hairs draw as thin lines (ask
for wisps); the strip in front of the ear is thinner than real hair there.

The older by-hand tie (`groom.tie` with gather rows, `curtain`, `frame`, below under groom_hair) stays for models
made with it; do not start new tied hair there: its curtain lays the front ACROSS the head.

## Loose hair: `groom.loose`

Hair that grows all over the scalp, is combed some way at its roots, then falls (or stands). It replaces the
generated tiers; the parting and hairline still apply. It is kept off the head, neck, shoulders and clothes by the
body's own signed distance, so it lies on the shoulders and down the back, and off the face unless it is a fringe.

| key | what | typical |
|---|---|---|
| length | m of hair from the root; or per region `{front, top, sides, back, nape}` (a layered cut, a short back and sides) | 0.3 shoulder, 0.5 mid-back, 0.04 a crop |
| level | every lock is cut where it crosses this height, m from the head centre (about the brows): a one-length cut | -0.105 jaw (a bob), -0.17 shoulders |
| spacing | m between lock roots (lock width follows) | 0.02 long hair, 0.015 short |
| body, lift | m the mass builds up as locks come down over each other; m of root volume (lift may be per region: the stand-off of a short cut; groom.volume does not reach loose hair) | 0.02, 0.006; curls 0.035, 0.012 |
| stiff | 0 hangs at once .. 1 keeps the direction it left the scalp in | 0.2-0.3 long, 0.6 short, 1 an afro |
| out | 0 combed along the scalp .. 1 straight out of it | 0; tousled 0.3; an afro 1 |
| back, messy, uneven | combed back over the crown; root directions turned at random; lengths differ | |
| flow | per region, the way the hair is combed there as a world direction [x his left, y back, z up] | front [0.55, -0.45, 0.7] (up and forward to his left), sides [0, 0.75, -0.65] |
| out, stiff per region | either may be {region: value} | a lifted front: out {front 0.3, top 0.12, sides 0}, stiff {front 0.9, sides 0.55} |
| ends | the ends turn under (+) or flick out (-) | a bob 0.5 |
| face | 1 = hair is turned aside where it would hang over the face (curtains beside the cheeks); 0 = it falls where it falls; or {"left", "right"} (the person's own sides: one curtain allowed over a cheek, the other kept clear) | 1 (keep 1 for long loose hair: below 1 the hair hung over the face in profile) |
| fringe | `{length, span (deg either side), depth (m behind the hairline), sweep (-1..1), level, stiff}`: combed forward over the forehead | length 0.07, level -0.004 (the brows) |
| fringe sweep "away" + curtain | CURTAIN BANGS: each side of the part swept down and away from it, longer toward the outer edges (`curtain` 0..1) | fringe {length 0.06, span 35, sweep "away", curtain 0.8} with parting centre |
| part_soft | true or {width (m, 0.015), cross (0..1, 0.25)}: a SOFT parting on loose hair (rule 5): roots beside the part are not combed sideways off it (that opened a bare V widening toward the forehead), the comb comes in over `width`, and a `cross` share of them is combed over the line. Pair with dense locks (spacing ~10 mm, width 2.4 on long hair: from above, 18 mm spacing left the whole top a patchwork of ribbons with scalp between) | true |
| tuck | `"left"` / `"right"` / `"both"` or {side, amount, from}: hair over and in front of the FOUND ear combed back behind it; `from` (deg of azimuth, default the temple) 10-15 tucks the front hair from the part too | one side tucked: "left" (the person's own). WHICH side a profile picture shows: check on a render through its fitted camera (a picture's "profile_left" name was the other side once): the untucked side hung a curtain over the face in profile |
| fade | {width, length, density}: the back's locks shorten and thin out toward the nape hairline (a barber's fade) | {width 0.02} on a short cut (the reader sets it) |
| halo, flyaway | 0..1: loose hair's own halo of fine hairs and its fly-aways (a TAIL's halo stays quartered; loose hair's is not: rule 4) | from the reader's halo density / wisps; long heads 0.5-1.0 / 0.05-0.15 |

The texture is the `strands` dials, not the groom:

| hair | groom.loose | strands |
|---|---|---|
| loose waves, shoulder length | length 0.3, body 0.024, stiff 0.3, uneven 0.5, spacing 0.021 | wave 0.014, wavelength 0.09, curl 0.25, clump 0.55, loose 0.45 |
| bob with a fringe | level -0.105, length 0.3, ends 0.6, uneven 0.15, parting none, fringe | wave 0.002, clump 0.4, flyaway 0.02, tips 0.15, taper 0.3 |
| long straight | length 0.5, stiff 0.2, messy 0.05, spacing 0.02, parting centre | wave 0.003, wavelength 0.16, clump 0.45, loose 0.2 |
| tight curls (ringlets) | length 0.22, body 0.035, lift 0.012, stiff 0.45, out 0.25 | wave 0.03, wavelength 0.028, curl 1, random 1, clump 0.85, clump_size 0.012, clump_shape 0.1 |
| afro (coils) | length 0.085, out 1, stiff 1, body 0, lift 0, spacing 0.02 | wave 0.03, wavelength 0.012, curl 1, random 1, clump 0.3, frizz 0.8, count 40000 |
| short tousled | length {front .05, top .055, sides .03, back .035, nape .018}, stiff 0.6, out 0.3, messy 0.7, spacing 0.015 | clump 0.4, tip_spread 0.7, loose 0.6, tips 0.8 |
| combed short cut (from the hair reader: `hair_from_reference`) | length {front .05, top .05, sides .018, back .018, nape .006}, lift per region = the measured stand-off - 5 mm, thickness 0.003, lay {front .35, top .65, sides .5, back .6, nape .6}, flow one way per region, messy low, spacing 0.005, width 2.4, body 0.004 (a continuous surface) | count 600000, thickness 0.9, clump 0.1, stray 0.9, loose 0, wave 0, curl 0, frizz 0.02, under_length 0.01 |
| short textured crop (a man's 2-3 cm cut, front lifted) | length {front .026, top .02, sides .022, back .022, nape .012}, spacing 0.009, width 2.4, lift 0.001, body 0.002, messy 0.35, uneven 0.8, flow + out + stiff per region (above), parting none, volume 3-4 mm | count 140000, thickness 1.6, clump 0.15, stray 0.9, roots 0.9, loose 0.18, frizz 0.15, wave 0.0004, curl 0, under_length 0.022; look scalp_tint 0.85 |
| short back and sides | length {front .045, top .04, sides .012, back .012, nape .006}, stiff 0.3, out 0.03, back 0.35 | clump 0.3, under_length 0.014 (the clipped sides ARE the scalp layer) |
| a child's fine hair | length 0.24, body 0.012, lift 0.004, stiff 0.2, fringe | thickness 0.6, count 60000, clump 0.2, clump_size 0.004 |

Curls: `wave` is capped at a third of `wavelength` (a wider swing folds over itself), so tight curls are small AND
short: set the wavelength (0.012 coils .. 0.03 ringlets .. 0.09 waves) and leave wave high. `random` above 0.6 lets
locks fall out of step and differ in wavelength: needed for curls (in step they are a crimped sheet with ridges
running round the head), wrong for a tail (pasta). `curl` 1 = a helix, 0 = a flat wave.

Looks of loose hair take in the bust: views `bust_front`, `bust_three_quarter`, `bust_side`, `bust_back`,
`bust_back_quarter`, `long_back`, `long_side`.

Cards of loose hair: under the cards lies a solid surface INSIDE the mass (`hair_cards.mass_shell`: the strands'
density meshed and decimated, faces toward the body dropped), so no air or skin shows between cards and a far tier
is little more than that surface; card vertices are kept off the whole body, not only the head.

## An existing sculpted groom as strands (a short men's cut)

A head that already has solid locks (hand-shaped or grown) becomes a strand groom without regrooming: the locks are
the guides. Worked on Garrett (624 thin hand locks, a short combed cut going grey), in this order:

1. `groom_hair(name, style="strands", strands={...})`. A short combed cut: `count` 100000, `clump` 0.3, `clump_size`
   0.006, `clump_shape` 0.5, `stray` 0.8, `loose` 0.4, `frizz` 0.2, `flyaway` 0.03, `tips` 0.6, `tip_spread` 0.5,
   `roots` 0.4, `under_length` 0.015, `wave` 0.003. Clump 0.4 with stray 0.6 at 60k strands read as strings.
2. **Grey.** A lock's own `grey` (0..1) is the SHARE of grey strands it grows, x `look.grey_locks` (default 1), plus
   `look.grey_amount` everywhere; `look.grey` is their colour. Locks made for the solid look often carry 0.35+
   everywhere: at grey_locks 1 the head is striped white. 0.6 was salt and pepper. The card tiers draw the same
   share (the locks' mean) in their pictures. The groom's DEFAULT temple / sideburn grey (`groom.grey` unset)
   follows the model's age: none to 30, all of it from 50 (`hair.grey_age`; a 19-year-old got grey streaks).
3. **Volume by measure.** Solid locks are modelled as thin shells on the volume; strands fill only each lock's own
   lens. Measure the outline against the reference (per level, mm per side), then `groom_hair(fuller={"sides":
   0.012})`: the locks rise and grow thicker by twice their lift, so the strands fill from the scalp up. (Lifted
   without thickening, a shell stands off the head over a short scalp layer; as solid locks the same lift is a
   stiff helmet.) Raise `count` with it: thicker locks spread the same strands thinner.
4. **The outline's cut.** Strands run to their lock's end and fan a little past it. A tapered nape is
   `groom_hair(trim={"below": -0.015, "where": ["nape"]})` (cut 15 mm INSIDE the hairline: the scalp layer carries
   the edge); with `below` positive it only removes what hangs over the skin.
5. **Colour in Cycles.** The hair BSDF's colour is not what a lit mass of strands renders as: uncalibrated, a dark
   grey-brown came out 3.5-4x too light. The look colour goes through a measured inverse (`hair_strands.CYCLES_FIT`;
   `look.cycles_fit: [1, 1]` turns it off). Mid and light colours land within ~5-40% of `look.lit`; near-black
   can't go under the highlights' own floor. Judge colour on the Cycles look, shape on the EEVEE one.
6. Dark slits between layers of locks are the scalp's tint in shadow (`look.scalp_tint`, default 0.85, made for
   dark hair): on grey or fair hair lower it (0.3-0.5; a grey crop with receded temple corners 0.15: at 0.5 the bare
   corners read as dark patches, hair-heads).

## Short cuts as a baked cap + sparse cards (crops, short back and sides)

A crop of 2-4 cm hair is not built like long hair. Cards cut one per clump read as torn paper or leaf litter at
bust distance, and cards only where hair stands off the head leave a bald dome inside a fringe (both tried on
Garrett). What game hair artists do, as far as it could be sourced:

- **The cap carries the look.** A mesh close over the skull wears a texture of the hair itself; breakdowns say a
  flat colour "can pass" but painted or baked fibres on the cap sell it, and for buzz cuts the advice is to bake the
  strand groom down into the head's texture (The Rookies breakdown; Polycount "hair study: shaved bun"; Thomas
  Pecht's buzz cut is described as "hair cards + baked hair cap, single texture"). Commercial short-hair assets
  ship colour, alpha, depth, direction (flow), id, normal, root and specular maps (3D Scan Store's real-time buzz
  cut); bake tools output flow, height, root / tip, normal and AO.
- **Cards over it are layers of falling opacity**: an opaque base that covers the scalp, then 2-3 sparser break-up
  layers, the last ones for the hairline and fly-aways (80.lv "Tips & tricks on hair for games"; Epic's Hair Card
  Generator: clumps of three cards, single-strand fly-away cards, a card group of its own for the hairline's short
  hairs, and for a buzz cut cards of two triangles). Root alpha fades so cards sink into the scalp; some cards
  stand across the others so the hair is not thick from one side and thin from the other (Polycount).
- **Shading**: anisotropic along the hair with a FLOW map on the cap (Reallusion's hair shader: the flow map
  "overcomes the obtuse look of low-poly hair cards"), depth / id / root packed for the shader (inZOI's mod docs),
  Kajiya-Kay or Marschner-style lobes (Scheuermann 2004; Karis 2016).
- **Alpha**: alpha test alone sparkles and thins with distance; mips must keep the alpha's coverage (Castano,
  "Computing alpha mipmaps"; Unity's mipMapsPreserveCoverage), or use alpha to coverage (Golus) or dither + TAA.
- Budgets seen: 5.3k polygons (a marketplace buzz cut), ~9k triangles single-sided (Jansen Turk's breakdown, which
  of his lengths unstated). Shell "fur" (copies of the mesh along the normals with strand dots) is documented for
  short fur, not found in a shipped human buzz cut.

What the tools build when a loose groom's mean lock is under 6 cm (`hair.SHORT_TIERS`; `hair_cap.py`):

1. **The cap's chart is baked from the strands.** Every strand of the groom (its locks' and the scalp layer's) is
   rasterised onto the scalp chart with a z-buffer by height over the scalp, each 0.55 mm wide in METRES (the
   chart's texels are ~0.3 x 0.1 mm and shrink toward the crown). Per texel: the top strand's value and whether it
   is a grey hair (each lock's own share, x `look.card_grey`, default 0.5: the top strand of every texel, fully lit,
   reads twice as silver as the same share among a path tracer's shadowed hairs), depth (how far it stands over the
   hair around it: the shade between hairs and clumps), a normal map from the strands' heights (`hair_cap.RELIEF`
   0.7 of the real slopes: the relief is what shades the hair darker away from the light), the strand's direction (the flow map). Under the
   strands an OPAQUE base wherever the groom is dense, from `strands.soft` inside the hairline: skin shows only
   where real strands are sparse. The chart is 2048 px; the atlas (tiles | chart) 4096 x 2048.
2. **The cap stands in the hair**, at 0.7 of the hair's height (its 85th percentile) over the scalp (`hair_cap.LIFT`, at most 15 mm), easing
   down to the skin over 12 mm at the hairline: the head's outline is hair, not a skull under a fringe.
3. **Cards everywhere the groom has length**, each standing at the TOP of its clump of strands (`hair.SHORT_TOP` x
   the clump's spread along its normal: a card on the clump's mean line is under the hair's outline), never under
   the cap, roots sunk in it, ending at the hairline (a card's few thick strands past it were wires on the skin), on tiles of a few
   THICK strands (16 / 9 strands a tile, 5-6 texels: a 1 cm card is seen 3-4 mips down, where a hundred 1-texel
   hairs are a grey film that an alpha test turns into a flake). The budget thins them evenly: cards that stand off
   the cap (the lifted front, the outline) and the hairline's go last. Tile strands are straightened (16 cm of
   wave squeezed onto 3 cm were white squiggles) and lit (the cap is the shade under them).
4. **One set of maps for every tier**: `export_hair(textures="shared")` (the default) writes hair_basecolor /
   normal / orm / aux / flow PNGs once and each `<name>_hair_<tier>.glb` refers to them by file name (they were
   embedded four times: 4 x 24 MB). `textures="embedded"` for a single self-contained GLB.
5. The material says KHR_materials_anisotropy with the flow map as its texture (direction in tangent space: red =
   along u, green = up the picture; blue = strength), roughness >= 0.85 (lower, with the strands' relief in the normal map, it shone like gel).

In an engine (checked in Godot 4.7, `spikes/godot_hair/look.gd`):

- **Mipmaps.** Images a `GLTFDocument` loads at run time have none; the strand texture then sparkles at every
  distance. Import through the editor, or `Image.generate_mipmaps()` on the material's textures. This was most of
  the "sparkle".
- Godot's glTF importer does not read KHR_materials_anisotropy, specular or sheen: set `anisotropy_enabled`,
  `anisotropy` ~0.35 and `anisotropy_flowmap = hair_flow.png` by hand (at 0.6 with the normal map the hair went
  metallic), and `vertex_color_use_as_albedo = true` (COLOR_0 is the cards' root-to-tip ramp).
- Alpha: glTF MASK imports as alpha scissor at the cut-off (0.33). The cap is opaque inside the hairline, so only
  the hairline's band and the cards depend on it; `alpha_antialiasing_mode = ALPHA_TO_COVERAGE` with MSAA softens
  both. Godot has no import option that keeps alpha coverage in the mips: the tiles' strands are drawn thick so they
  survive it.
- The hero tier (16k) spends its extra triangles on a finer cap and twice the cards; at bust distance it is hard to
  tell from main (8k). Use main unless the camera goes closer than a bust shot.

Sources for this section: The Rookies, a real-time hair breakdown (https://www.therookies.co/projects/65082);
Polycount "Hair study: shaved bun" (https://polycount.com/discussion/237326/hair-study-shaved-bun) and "How should I
texture characters hair" (https://polycount.com/discussion/160776/how-should-i-texture-characters-hair), read as
search snippets; 80.lv "Tips & tricks on hair for games" (https://80.lv/articles/tips-tricks-on-hair-for-games/);
Epic, Hair Card Generator (https://dev.epicgames.com/documentation/unreal-engine/hair-card-generator-for-grooms-in-unreal-engine);
3D Scan Store real-time buzz cut (https://www.3dscanstore.com/hair/realtime-hair-buzzcut); Reallusion's hair shader
textures (https://manual.reallusion.com/Character-Creator-4/Content/ENU/4.0/15_Digital_Human_Shader/Hair/Textures-3-4.htm);
inZOI mod docs, hair texture set-up (https://mod-docs.playinzoi.com/docs/modkit-docs/modkit/project/caz/hair/05-texturesetup);
Castano, "Computing alpha mipmaps" (https://ludicon.com/castano/blog/articles/computing-alpha-mipmaps/); Karis, "Physically
based hair shading in Unreal" (https://blog.selfshadow.com/publications/s2016-shading-course/karis/s2016_pbs_epic_hair.pdf);
Godot forum, run-time glTF textures without mipmaps (https://forum.godotengine.org/t/not-applied-mipmap-at-gltf-runtime-loaded-model/94799);
Godot's gltf_document.cpp (no anisotropy / specular / sheen extension). No numbers for a short cut from a named
studio talk were found; a strand's width in texels and "bent normals for caps" have no source (ours by measure).

### Laying a crop: `groom.loose.lay`

A short cut's height is not its length. Measured on Garrett's crop: `stiff` 0.6 on top stands it up as a brush
(+15 mm over the photo's outline), `stiff` under ~0.3 lets gravity curl 3 cm locks into hooks, and cutting the
length changes little. `lay` (0..1, or per region) presses each lock's direction onto the head as a comb does:
`{"top": 0.4, "front": 0.15}` took the top from +6-10 mm to 0 at `stiff` 0.4-0.5 with no hooks. Regions are broad:
"top" reaches the upper sides, so check the sides' width after laying the top (they thinned 4-7 mm) and give them
`out` back. A hairline moved up adds height (the front roots stand higher on the head).

### A front swoop and a combed-down back
`groom.loose.swoop` {at, span, depth, rise, sweep, stiff, length, body, lay} lifts the front lock up and back and
over to one side as ONE lock (its locks combed in step, wider and thicker, strands kept together); the game cards
give it its own layered cards (hair.SWOOP_*). `messy` takes regions too: tousled on top, low at the back and nape
(`{"front": 0.45, "top": 0.4, "sides": 0.2, "back": 0.08, "nape": 0.05}`). A short back that reads curly is short
locks hooked by `stiff` + `lay`: give the back and nape some length (25-30 / 15-20 mm), `lay` 0.6-0.7, `flow`
straight down; an 8 mm nape left the scalp tint showing as a dark band even in the strand look.

### Drawing the cards in an engine
Judge game hair in the game's renderer. `spikes/godot_hair/hair_cards.gdshader` (README beside it) is a reference
Godot shader for the exported cards: two shifted strand highlights along TANGENT's bitangent, wrapped diffuse, the
aux texture's root / clump shade, alpha-to-coverage. Godot's own StandardMaterial reads none of the aux texture
and draws the cards as a fine uniform hatch. Back faces: the cards share one normal on both faces; an engine that
flips it on back faces (Godot does) draws a black fringe round the outline: un-flip it in the material. Not yet in
any game.

## Limits today

Cards are still smoother than strands at bust distance (less strand-to-strand contrast), a few dark slits show
between cards on a combed-back top, npc cards lift at the crown like roof tiles, and the far tier is a helmet and a
solid tail without wisps. The atlas is a numpy raster of Blender-evaluated strands (alpha, per-strand id, depth,
root gradient, a normal from depth), not a Cycles bake; a short cut's cap has flow, depth and a normal from the
strands' heights, long hair's cards only a constant flow. Clearance is checked
against the head as the scalp's rays see it, not against a game's decimated skin. Loose long hair has no core
surface (only tied tails do): its coverage is the dense first layer.

## Tool reference

The full documentation of this topic's tools: their MCP descriptions are the short form. guide(topic="<tool name>") returns one section. These tools are the `hair` toolset: enable_toolset("hair") turns it on.

### `groom_hair`

`groom_hair(name, groom=None, replace=False, stage=None, note='', style=None, strands=None, look=None, fuller=None, trim=None)`

Grow the hair's locks from spec["hair"]["groom"] (the designer's words and numbers) and save them.
Hair is curve locks (Bezier curves swept with a cupped lens profile) in the model's Blender scene, not part of
the SDF body; guide(topic="hair") is the workflow. Needs a head with face landmarks (a `base` head) or a
groom "centre" joint.
groom: a patch merged into the stored groom first (objects merge key by key, null deletes), e.g.
  {"volume": {"top": 0.04}, "parting": {"side": "left", "offset": 0.03}, "drawn": [...]}.
  Keys: hairline (front, temples, sideburns = m below the FOUND ear's top, nape, ear = m over it, ear_from "mesh" | "brow", front_points), parting (side, offset, length, line, flat,
  full, depth), volume (front, top, crown, sides, back, nape: m of hair over the scalp; ramp, across, crest: x of the top's crest, taper: {from, to, floor} short tapered sides and back), length
  (per region, m), flow (per region: {"back"|"down"|"up"|"away"|...: weight}), tiers ({tier: {width, thickness,
  spacing, where, length, taper, belly, root, ...} | false}: strip = shingled side/back strips, gap = covers
  bare volume, big/crown = the generated top, fill, edge), drawn (big clumps drawn by hand: [{"name", "top":
  [[x, y] m from the head centre seen from above, root first] | "azel": [[az, el] deg], "width", "thickness"?,
  "taper"?, "lie"?, "root"? (width at the root: 0.1 grows out of the layer), "climb"? (m the root takes to rise),
  "to_hairline"? (inset m or {inset, reach}: the edge laid on the hairline), "split"?}]; name rows stem+number so
  an under-layer clump fills between neighbours; patch one by name: {"drawn": {"sweep2": {...}, "qf*": {...},
  "old": null}}), hairline_edge ({inset, reach} for every clump near the hairline), volume.edge_sink,
  parting.front, grey, noise, seed.
  tie ({"at": [az, el] deg (az 180 = the back, el up), "out": m off the scalp, "gather": {rows, locks, lift,
  width, uneven}, "tail": {length, fullness, locks, stiff, uneven, taper, coil, plait}, "escape": n wisps the tie
  missed, "band": m, "curtain": {span deg, to deg, over deg, lift m}: the front from a soft part sweeps down and
  out over the temples and the ears' tops before it turns back (a loose low ponytail; without it every lock runs
  straight back), "frame": {count a side, az [a0, a1], length [l0, l1], width [w0, w1], wave, wavelength}:
  styled face-framing pieces in front of the ears, soft and wavy, mixed lengths}: hair gathered over the head into a
  tie and a tail leaving it; parting.side "none", or "centre" with a short soft part (length 0.04, width 0.006,
  depth 0.4: no bare furrow running back).
  A LOW or SIDE tie (a low side ponytail): gather {"toward": "crown", "rows": 4, "locks": 80, "reach": 0.9,
  "inner_roots": 0}: by default the inner rows root on the way to the tie, which for a low side tie leaves the far
  side of the top to the hairline row alone (a headband round the hairline, a bare wedge behind the part, stubble
  on the crown: look from BEHIND and from the far side, the references' cameras never show it);
  gather.hairline_strands {"density": 2, "clump": 0}: the hairline row is the one that lies over bare skin at the
  temples (thin there, its sub clumps draw as contour lines on the skin).
  curtain {"arch": deg, "arch_at": deg}: rounds a pointed forehead (the two curtains run straight diagonals from
  the part: a triangle): the run over the forehead raised for locks rooted arch_at deg from the part, none at the
  part (a negative dip does it by closeness to the part: the centre rises and bares a notch); per side
  ("left"/"right": {"arch": ..}) when one corner needs more. "smooth": rounds of smoothing where the way's arcs meet.
  frame {"hairs": 3, "curve": 0.14, "count": [10, 6], "width": [0.001, 0.003], "strands": {"clump": 0, "flyaway":
  0, "flat": 1, "loose": 0.9}}: loose SINGLE hairs beside the face: each piece is 1..hairs strands in their own
  object (a lock is never under ~8 strands side by side: comb strips; more of those is worse), bowed off its line
  in its own plane. look.fine_alpha (0.5): EEVEE draws single hairs part transparent (a strand is never under a
  pixel wide; Cycles draws true widths).
  tail {"sway": 0.016, "sway_length": 0.22, "flick": 0.022, "strands": {"clump": 0.55, "tips": 0.9, "tip_spread":
  0.1}}: big soft waves = the tail's AXIS swings (strand / lock waves only crimp a straight tail), flick turns the
  locks' ends out, a lock's own clump / tips make pointed separate locks instead of a blunt brush),
  loose ({"length": m | {front, top, sides, back, nape}, "level": m from the head centre (a one-length cut ends
  there: about -0.10 the jaw, -0.17 the shoulders), "spacing": m between lock roots, "body": m the mass builds
  up, "lift": m of root volume, "stiff": 0 hangs .. 1 keeps its root direction, "out": 0 combed along the scalp
  .. 1 straight out of it, "back": 0..1 combed back over the crown, "messy", "uneven", "ends": + under / - out,
  "face": 1 = kept off the face, "fringe": {length, span deg, depth, sweep, level, stiff}}: hair grown all over
  the scalp that FALLS on the neck, shoulders and back (or stands: an afro is out 1 + stiff 1 + curl): a bob,
  loose waves, long straight hair, a fringe, a crop, tousled hair. guide(topic="hair") has recipes per style).
style: "locks" (solid sculpted locks: stylised hair, the default), "strands" (the locks become GUIDES of a strand
  groom on Blender's Hair Curves: realistic hair; the game export cuts cards from those strands), "cards".
strands: a patch of the strand dials (hair.strands; guide(topic="hair"), "Strand grooms"): count, thickness,
  taper, clump, clump_size, clump_shape, stray, tip_spread, loose, wave (m), wavelength (m), curl, random, frizz,
  flyaway, tips, roots, under, under_length, flat, soft, baby. look: a patch of the material (lit, gap, tip,
  tip_amount, vary, root, roughness, light "salon" | "flat").
  look, the colour model (strands): variation 0..1 (default 0.4), sun 0..1 (sun-lightened lengths, by the hair's
  age from the scalp; default 0.2), highlights 0..1 + highlight_contrast (lighter warmer ribbons; default 0),
  fly_light 0..1, depth 0..1 (under-layers of hair with volume darker), root_dark 0..1, gloss 0..1 (the two
  highlight lobes in EEVEE). Flat on purpose: variation 0, sun 0, vary 0. The groom export carries the model as a
  per-point `groom_color`, the game cards as vertex tone (hair_colour.py).
  look also: grey_amount (share of grey strands everywhere), grey_locks (x each lock's own "grey": greying
  temples and sideburns are locks with more grey), grey (its colour), scalp_tint, cycles_fit.
fuller: {region: m} (front, top, sides, back, nape): the EXISTING locks made fuller there, as a barber's "more at
  the sides": every lock point rises by that much (eased in from the hairline) and the lock grows thicker by twice
  its lift, so a strand groom fills from the scalp up; negative = closer. Measure the outline against the
  reference first (hair_reference's outline_regions, in mm) and give the miss. Solid sculpted locks ("locks")
  are only lifted (thickened they'd be slabs). trim: {"below": m, "where": [regions]} (or a list): every lock is
  cut where it runs more than `below` outside the hairline in those regions (negative = cut that far INSIDE it:
  a tapered nape is {"below": -0.015, "where": ["nape"]}). With only fuller / trim given nothing is regrown.
stage: "mass" shows only the groom's volume as one shell (judge the silhouette first), "locks" the locks.
Locks edited by hand (in Blender and pulled, or by edit_model) carry "hand": true and are kept; locks deleted in
Blender (hair.removed) aren't grown again; replace=True regrows everything and forgets both.
Edit single locks with edit_model: {"op": "set", "kind": "hair.locks", "name": lock, "value": {"width": 0.07}};
the material with {"op": "set", "kind": "hair", "name": "look", "value": {"lit": "#5a3a2c"}}.
Then look_hair. Returns the counts per tier.

### `tie_hair`

`tie_hair(name, style=None, carry_from=None, look=None, note='')`

A tied-back hairstyle from a STYLE (stored as spec.hair.groom.tied; see "Tied-back hair as a STYLE" above for the
table of words): style is MERGED into the model's tied style (name only what changes: a riff), the hair becomes a
strand groom (hair.style "strands") and is regrown; any groom.tie / groom.loose the model had is replaced by what
the style makes. carry_from: first wear that model's whole hair (hairline, look, strand dials, tied style), scaled
to this head (traced hairline heights move with the head centre). look: a patch of the hair's material.
style keys: tie (nape | low | mid | high | top | deg), side (centre | left | right | deg, the person's own),
tightness 0..1, lift 0..1, volume (0..1 or {amount, crown, sides, nape, root, arc, layers, hold}: the hair stands up
from the roots / the part and arcs over, in layers; 0 = a cap on the skull; default = lift),
part (centre | left | right | none), ears (tucked | covered), tail ({kind: tail | bun |
plait | none, length m, fullness 0..1 (sleek .. bushy), wave 0..1 (straight .. loose waves), tousle 0..1 (brushed ..
a ragged end and strays), to: back | shoulder} or just the kind), wisps (0..1 or {amount, where: [part, front, temple,
sideburn, nape], length [m, m], softness 0..1, loose: n thick locks a side}: soft clumps of fine hairs at the hairline;
default from neatness), front (0..1 or {looseness, drape, locks}: the hair in front of the ears alone looser, hanging
over the forehead corners, with thick loosened locks), hairline (0..1: 0 = a hard edge, 1 = thins out with baby hairs; default 0.8 - 0.3 x
neatness), escaped (single hairs: n a side or
{count, where, length}; default none), neatness 0..1, half (true) + length m, detail ({"tie": .., "strands": ..}: hair_tied's own
keys, when a word is missing).
Returns what was grown (gather / tail / wisps / escaped hairs), the style as stored, and what it made in numbers (the
tie's place, how far the hair stands off the head, the tail). Then look_hair(name, views=["around"]) (needs `sync`
once). Heavy the first time on a body (its collider, ~1 min), 1-2 s after.

### `look_hair`

`look_hair(name, views=None, size=480, clay=True, layout=False, reference=None, save=None, only=None, tier=None, debug=None, engine='eevee', stage=None, measure=None)`

A fast look at the hair (4-30 s): the head cropped from the model's Blender scene with the hair from the spec,
rendered in EEVEE. Rows: the material, the same in clay (shape without colour: judge clumps there), and with a
matched reference camera (hair_reference) the matched render, its clay, the reference, a 50% blend and the traced
lines over the render (reference yellow, model cyan). A thumbnail shows how it reads small.
views: any of front, three_quarter, three_quarter_r, side, back, top, close, close_back (default front,
three_quarter, side, back, top); "around" = six sides with the bust (bust_front, bust_three_quarter, bust_side,
bust_back_quarter, bust_back, bust_side_r): the row for hair that hangs and for the angles nobody tuned. layout=True adds the groom seen from above as a sketch: hairline, parting, every
lock's spine (drawn clumps black with names, others by tier), roots and tips; views=["layout"] gives only that
(no render). reference: an image to show beside the views (default: the traced reference). only: lock names or
patterns (["sweep*", "pside0"]) shown alone on the underlayer, to see which locks make a busy patch (the gates
then measure that subset).
Returns the images and the measured gates: the outline's dents (front, 3/4: a pinched temple reads as a divot),
the bare-volume share per view (the volume showing between locks reads as a helmet), and with a trace the fit to
the reference (part start px / direction deg, hairline px, silhouette IoU, outline px, clump directions).
A strand groom (hair.style "strands") renders its strands; engine="cycles" path-traces them with the hair BSDF
(the truthful look; minutes, and it waits for the machine's heavy slot). tier: "hero" | "main" | "npc" | "far"
shows the game CARDS of that tier instead (cut from the strands); debug then isolates what makes a fault:
"layers" (cards as solid quads coloured by layer: cap grey, 0 red, 1 green, 2 blue, 3 yellow), "cap_only",
"cards_only", "no_normal", "unlit". export_hair judges the exported files themselves.
views "ref0", "ref1", ...: the FITTED cameras of the model's reference pictures (human_refs.json: the block-in /
face solve's cameras), the whole picture squared: the hair as each picture shows it, always the hair of the spec as
it is NOW (a look never reads a mask or render back from an earlier one).
stage: another model with the same head whose scene is used (a riff's copy of a head needs no scene of its own:
`look_hair("riff", stage="the_head")`).
measure: {"view": "ref2", "mask": png, "tie": [x, y], "colour": true}: the current hair against that picture. mask =
a hair mask in the picture's own pixels (white = hair); the text then gives IoU, area, the outlines' distance (mm)
and, with tie = the tie's pixel in the picture, what hangs below it against hers (area %, length, width, reach in mm).
colour: CIE L* / chroma / hue of the dense hair's shadow / mid / highlight thirds, ours | the picture's, and
`variation` (hair.colour_variation: L_sd, strand_sd (against its 1.5 mm neighbourhood), ribbon_sd (1.5 mm against
9 mm: clumps, highlight ribbons), mass_sd (9 against 40 mm: form, roots / lengths), ribbons {share, contrast} = the
share of the hair that is a LIGHT ribbon and its lift in L*, chroma_sd, hue_sd): set look.variation / sun / highlights
by these (Tess's pictures: ribbon_sd 3.1, light ribbons 10 % of the hair at + 5.8 L*; a flat look reads ~2 and 3 %), for the
engine rendered: the numbers to set look.eevee_gain / eevee_sat (EEVEE) or look.cycles_fit / cycles_width /
cycles_sat (Cycles) by. The look's own lights are used (look.light), not the picture's: compare bands, not single
pixels. (Sheets before th_30 labelled "Cycles" were path-traced with 2 transmission bounces, which renders dark hair
near black; look_hair(engine="cycles") uses 10.)
Needs the scene once: `sync` the model (or its stage) first.

### `hair_from_reference`
`hair_from_reference(name, out="", read_only=False, authority=None, compare=None, seed=0)`: the HAIR READER. The
model's fitted reference pictures (human_refs.json, from the block-in / face solve) are MEASURED, never used as a
texture (as skin_from_reference): face parsers (MediaPipe multiclass + BiSeNet) give hair / skin / backdrop, a
pixel-level hairness runs from the backdrop's colour to the dense hair's, the model's scalp projected through each
camera is the bare skull. It reads:
- stand-off (mm from the skull's edge to the solid hair's edge, by region: front, top, crown, sides, back, nape; per
  view and the median; NEGATIVE where the skull pokes through the hair = the head and the picture disagree there:
  fix the head or trust another view, not the groom) -> rule 1
- halo density (mean hairness 0.5-4 mm past the solid edge: 0 a cut-out .. 1 solid), edge roughness (mm against its
  own 15 deg trend), wisps (detached hair pieces within 12 mm, per 10 cm of outline) -> rules 4, 7
- hairline: every hair / bare-skin boundary pixel cast onto the scalp (height per |az|, left and right together, and
  their difference), softness (20 -> 80 % hair across the line, mm), baby hairs (thin specks on the skin side, per cm)
  -> rule 6
- parting: a sharp flip of the strands' direction over the top WITH a line of scalp (front-ish views); else NOT SEEN
  and the start has no part (INFERRED); the front's sweep (which way it is combed) -> rule 5
- colour from ONE authority view (default the most frontal; the others are printed as checks: pictures disagree on
  colour between views): colour_bands + colour_variation, a two-mode split into pigmented hair (`seen`) and light /
  grey strands (`grey`, their share), and the light share BY REGION (salt and pepper greys at the sides first)
  -> rules 8-11
- length: not in a picture of a short cut (it lies over itself): INFERRED from the stand-off.
The START (saved to `out`, a copy, or the model; read_only shows it without saving): style strands; a short cut
(mean stand-off < 30 mm) gets `groom.loose` as a combed short cut (rule 14): lengths by region (INFERRED: a taper),
`lift` per region = the stand-off less the strands' own ~5 mm (groom.volume does nothing to loose hair), thin laid
locks, flow one way per region (the front over by the measured sweep), lay (prior), hairline front_points (MEASURED),
parting (MEASURED or none), grey by region; look seen / grey (a grey STRAND: the lightest quarter of the light pixels,
since strands finer than a pixel mix with dark ones) / grey_amount / variation; strands: fine, straight, dense, with
halo / flyaway / soft / baby from the read. `colour_step` (in the compare reply) then corrects seen and grey per
linear channel by picture / render on the authority view: one step took the mean L* from 30 to 40 (picture 42).
Longer hair: hairline, parting and look only (groom the shape by hand). Every line says what it came from.
`compare={0: "s_v0.png", 1: ...}`: the same read on OUR renders through those fitted cameras (square renders as
look_hair's "ref<i>" views), as a table ours | picture: the round's measure, like with like.

### `hair_reference`

`hair_reference(name, trace=None, image_path=None, apply=False, widen=1.8, save=None)`

Match the hair to a reference picture: store its trace, fit the reference's camera to the model's face, and
 optionally carry the traced groom onto the head. From then on every look_hair adds a matched row and fit numbers.
 trace (or the stored one when omitted): see below; trace it by reading pixels off the image (zoomed crops with
 a grid help). image_path sets/overrides trace["image"].
 The camera (pose + focal length) is solved by least squares from trace["landmarks"] (the model's lm_* joints ->
 their pixels); expect a few px of error per landmark, more means a mislabelled point.
 apply=True: the trace carried through the camera onto the head becomes the groom's parting line, hairline
 front_points and drawn clumps (rays onto the groom's volume; hidden roots carried back to the part; rows behind
 the traced ones; widths = traced px x mm/px x widen, since clumps overlap) and is merged into spec.hair.groom.
 Then groom_hair to grow the locks, and look_hair.
 Returns the trace drawn on the reference (landmarks green, the fitted camera's reprojection cyan) and the errors.
 A trace is reference-image pixels (u right, v down) of the picture you're matching:
   {"image": path (or pass image_path), "landmarks": {lm joint: [u, v], ...} (8-10 face points: eye corners, brow
    middles, nose tip, mouth corners, chin; the model's lm_* joints), "part": [[u, v], ...] (the parting from its front
    end back), "hairline": [[u, v], ...] (temple to temple across the forehead), "hair": [[u, v], ...] (closed outline of
    the visible hair above clip_y), "clip_y": v (below it ear, sideburn and beard aren't traced), "clumps": [{"name",
    "line": [[u, v], ...] root -> tip along the strands, "width": px across the clump}], "crop"?: [x0, y0, x1, y1] (the
    square the matched views show; default: round the hair and landmarks), "views"?: {name: {the same keys for
another view of the character: another figure in the same picture (same lens), or a turnaround's side/back with
its own "image"; landmarks, hair, hairline, clip_y and crop needed}}}. Every view gets its own matched row and
outline numbers in look_hair.
 Clump names: one starting "part_side" is the short clump falling from the part toward the near ear; one whose root is
 across the head from the part is the sweep's fall down the far side; the rest are the rows sweeping from the part,
 front first.

### `export_hair`

`export_hair(name, out_dir, tiers=None, groom=True, check=True, save=None)`

The hair alone, game-ready, from a strand groom (hair.style "strands"; guide(topic="hair"), "Strand grooms"):
one GLB a tier in out_dir (`<name>_hair_<tier>.glb`; tiers hero 40k / main 16k / npc 6k / far 1.5k triangles;
default main, npc, far), all on ONE atlas: cards cut from the groom's own strands (a lower tier = fewer, wider
cards from bigger clumps; far = the cap + a solid tail), the cap wearing the scalp's chart, alpha MASK, two
sided, the recipe for an engine's hair shader in the material's extras. groom=True also writes the strands
(`<name>_groom.abc` in cm for Unreal's groom import, `<name>_groom.usdc` with groom_* primvars).
check=True re-imports every GLB on the head (as an engine gets it) and judges it against the strands in the same
views and light, under a hard alpha TEST and dithered: per view iou / bare (strand silhouette left uncovered),
value and saturation x the strands', detached rectangular blobs (cards showing as stamps), straight outline
share (plank ends), with WARNING lines. save: the sheet (strands | each tier alpha test, dithered, cards as solid
quads by layer | the atlas); each row is also written beside it as <save stem>_<tier>_<test|dither|solid>.png.
Minutes with check (about one a tier). Returns the sheet and the table.
