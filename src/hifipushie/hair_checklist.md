# Hair: what makes hair read as hair (the checklist)

Read guide(topic="hair") first: describe the hairstyle in words before touching a knob.

Judge each, one area at a time, against the reference in the same camera (`look_hair(views=["ref0", ...])` or
fitted-camera close-ups); fix in this order. A rule's MEASURE is how to check it, its KNOB what sets it.

| # | rule | the fault when it is missing | measure | knob |
|---|---|---|---|---|
| 1 | The mass stands OFF the skull: real hair is ~1.5-2 cm off the skull over the top and sides, 3-4 cm above a low tie | a combed cap hugging the skull ("flat") | outline stand-off from the skull through the fitted camera (`hair_from_reference` stand-off by region, mm); in a ROOM (a couch, a shirt) the stand-off only counts where hair meets the backdrop: compare the outline's width per height in front and its reach behind the skull in profile instead | `volume` (amount, crown / sides / nape, hold); loose long hair: `groom.loose.body` (the lengths fill out as locks come down: 8 -> 25 mm took a lank head to her mass), waves in the lengths (`wave_from`) |
| 2 | From the parting the hair RISES and arcs over, then falls down the side: convex arcs, not straight lines to the tie | straight diagonal strands laid flat | strand paths from the part traced on both pictures; the groom from above (`look_hair(layout=True)`) | `volume.root` (bend radius), `volume.arc` |
| 3 | The mass is LOCKS with depth, not one shell: under-layers darker, locks of different height and width | a smooth helmet | by eye in close-ups; colour_variation `mass_sd` | `volume.layers`, `volume.locks` (keep <= 0.4: at 1 the crown's silhouette is wavy wires), look `depth` |
| 4 | A HALO: fine, light, slightly curly hairs standing a few mm off the top layer along the whole silhouette | a surface, not hair (the strongest single tell) | by eye at the silhouette in front / profile; hair_from_reference: halo density, wisps / 10 cm (compare= ours vs picture) | `wisps.halo` (default with volume; gentle curls, never the old `strands.halo` on every lock: a wire grid); LOOSE hair: `groom.loose.halo` / `flyaway` (its free locks were quartered like a tail: on long heads it read a third of the picture's halo) |
| 5 | The PARTING is a soft line: hair rises and falls both ways, crosses it, scalp barely shows; it fades out a few cm back | a clean notch between two lobes, dark roots | close-up of the part from the front | `hairline` (zig), `volume.cross`, halo crossing (28 % of `wisps.halo`), part rows drawn fine |
| 6 | The HAIRLINE thins out over ~1 cm with fine baby hairs; the temple is hair down to the ear | a hard dark edge, a shaved temple, a grey veil | close-ups of both temples and the forehead's corners | `hairline`, `wisps.baby`; the ear is found on the mesh (hair.ear) |
| 7 | WISPS / escaped strands are fine, near-straight with a soft bend, a little lighter, hanging close to the face | corkscrew ringlets (doll-like), black wires, a grey veil of flat clumps | close-ups of the temples and in front of the ears | `wisps.curls` (escaped strands), `wisps.amount`; flat clumps are cut back automatically under volume |
| 8 | COLOUR varies like real hair: per-strand and per-ribbon variation, darker roots, lighter older lengths, light ribbons ~10 % of the hair | "one flat brown" | `hair.colour_variation` (look_hair measure colour): one measured photo: L_sd 7.5, strand_sd 4.2, ribbon_sd 3.0, light ribbons 9-10 % at + 5.7 L* | look `variation`, `vary`, `highlights` + `highlight_contrast`, `root_dark`, `sun` |
| 9 | LIGHTENING is lighter AND warmer, never greyer; the overall colour by measure (chroma, hue) | ashy grey lengths; ginger when overshot | colour_bands chroma / hue against the picture (e.g. a mid brown: chroma 8-9, hue ~69) | look `lit`, `gap`, `eevee_sat` (~0.4), `sun` |
| 10 | Highlight RIBBONS are irregular: a few broad soft ones and many thin, fading along their length, on the top layers | regular pinstripes; flat tan painted bands | colour_variation `ribbons.share` / `contrast`; by eye | look `highlights` (two scales built in) |
| 11 | A light catches the hair: a sharp pale lobe toward the root and a broad warm lobe toward the tip (Kajiya-Kay / Marschner R and TRT) | matt, grey, plastic | a lit close-up of the dome beside the photo | look `gloss` (EEVEE; ~0.6). Cards: the card material's anisotropic two-lobe specular along the tangent (the cards carry tangents) |
| 11b | Thin hair GLOWS: tips and fine / single hairs lighter and warmer (light through them), and see-through toward the tip | an opaque cut-out silhouette, solid tips | colour_variation `edge_L` vs `core_L` (a photo's outline thin hair is ~2-5 L* lighter than the mass) | look `backscatter` (a translucent, back-lit warm term weighted to thin hair), `tip_alpha` (dithered alpha over the last 30 % of a strand). Cards: the atlas already fades its tips' alpha; back-scatter is the card material's transmission / subsurface term (UE groom: dual-scattering; a card shader: a back-lit wrap term) |
| 11c | The CORE of the mass is darker and richer than its outer layers (multiple scattering inside a mass) | one flat value through the mass | colour_variation `core_L`, `core_chroma` | look `scatter` (by a lock's depth hp_sh: darker, more saturated) with `depth`. Cards: the cards' vertex colour carries depth (lower layers darker); saturation is a card-material tint |
| 12 | A TAIL is strands from behind, not wide ribbons: finer strands, locks a little out of step, a ragged soft end | wavy ropes / ribbons, straw | back three-quarter beside the photo; tail area / length / width by mask (look_hair measure) | `tail.wave` (~0.35), `tail.fullness`, `tail.tousle` |
| 13 | Up-styles (high ponytail, top knot, man bun) and half up have NO volume by default: hair pulled up does not fall from its roots | radial ridges round the hairline, specks at the crown | the riffs sheet | volume is gated by tie height and half up; asked for there it is a smooth pouf |
| 14 | A SHORT CUT has LENGTH AND LAY BY REGION: longer on top and front (4-6 cm), clipped sides and back (1-2 cm), a taper to the nape (~0.5 cm, a soft edge); combed ONE way per region; fine, straight, dense strands | long-hair machinery on a crop: wavy clumped noodles, wings at the sides, a curly astrakhan back (laid locks thicker than twice their clearance sink half their strands into the skin and crumple when pushed out) | `hair_from_reference` stand-off by region ours vs picture (`compare=`); the back and nape close-ups; the lock plot | `groom.loose` length / lay / flow / lift (per region), `thickness` <= 3 mm; strands: count 200k+, thickness ~0.9, clump ~0.1, wave / curl / loose 0 (the reader's start sets these) |
| 15 | FINE strands at the picture's scale: short hair at bust distance is a near-continuous fine texture; strand-to-strand contrast as the picture's | wires, straw, a hairline of comb teeth (each lock's strands start as one blunt row) | `hair_from_reference(compare=)` colour variation `strand_sd` ours vs picture (e.g. 9.3 vs 6.8: too coarse) and hairline softness (1.0 vs 3.5 mm) | strands `thickness` / `count` / `clump`, `fly_light` lower on grey hair, the hairline's density ramp (`soft`, `baby`): NOT yet enough on a crop. DENSITY that reads as one combed surface is the LOCKS' coverage, not the strand count: `groom.loose` spacing 5 mm, width 2.4, body 4 mm (+ count 600k) closed the scalp-between-ridges look on a crop; count, thickness, clump and stray alone barely moved it (isolated one at a time) |
JUDGING RENDERS AT A PICTURE'S SCALE SUPERSAMPLE: EEVEE draws every strand at least one pixel wide, so at a photo's
own scale (~0.3 mm a pixel for a head-and-shoulders picture) a 0.05 mm hair is drawn as a 0.3 mm wire: the hair reads
coarse and wiry whatever the strand dials say. Render 2x and average down with more
strands (count ~300k on a short cut) before judging rules 3, 8 and 15 against a photo; coverage drops, so redo the
colour step afterwards (mean L* fell ~6 on the man's crop). A game gets the same from TAA / alpha-to-coverage on thin
cards, not from thicker strands.
Before a change ships: re-render the styles you already accepted beside their accepted renders (same cameras, same
seeds: renders are deterministic) and look at the differences, so a fix can't silently break what worked.
Isolate a fault before fixing it: render the groom with one piece off at a time (`look_hair(only=[...])`, one dial at
0, one lock pattern dropped): a wire grid on the crown was the halo dial, a grey veil the flat wisp clumps, a dark
tangle at the part's start the far bank's strands seen end-on.

## Strand dials (`strands`): the character of the hair

Set with `groom_hair(name, strands={...})` once the shape is right (all 0..1 dials unless a unit is given; they
cannot reach values that stop reading as hair):

| dial | what it does | when wrong |
|---|---|---|
| count | strands in a look (30k default; more for a close-up) | too few: see-through |
| clump, clump_size (m), clump_shape | strands gather into sub clumps; where along the strand | 1 / shape 0: ropes |
| stray | share of strands that only half join their clump | 0: each clump a rope with air between (pasta) |
| wave (m), wavelength (m), curl, random | the lock's swing; `random` = how far sub clumps fall out of step | random 1 on a tail: pasta |
| loose, frizz, flyaway | strands wandering together / singly / letting go | frizz high: a cloud |
| tips, roots, taper | ragged ends, staggered roots, strands thinning to a point | tips 0: a cut brush |
| under, under_length (m), soft (m), baby | the scalp layer and the hairline's fade | under 0: skin through the hair |
| halo | short broken hairs standing up off the hair and curling (the fuzz round a loose updo against the light); flyaway strands only drift mm off their lock and end where it ends, so flyaway alone shows no halo | 1: a bristly brush; 0.5 a soft fuzz |
| halo_soft | 0..1: the halo DENSE AND SOFT: up to 4x the halo hairs, ~4 mm off the hair and ~2 cm long (a fuzz along the silhouette, not a few hairs standing off); pair with look `fine_alpha` 0.2-0.3. Matched a grey crop's halo; not enough on long dark hair | 0: the old single halo hairs |
| free: {dial: value} | the dials of hair that has LEFT the head (a tail) where they differ: a tousled top (loose 0.7) with a tail of defined wavy locks (free loose 0.2-0.35) | loose 0.7 on a tail: crimped wool |
| on one lock: strands {clump, tips, roots, density} | that lock's own share of the object's dial | |

A thin lock (< 16 mm) is a wisp: it swings less and slower by itself (at a lock's wave a few hairs side by side
read as crimped ramen). Hair gathered into a tie narrows into it and every strand reaches it.
