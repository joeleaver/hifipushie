# Skin: every stage in detail

Read guide(topic="skin") first: read the skin from the reference before setting anything.

## The stages (do them in this order; look after each)

Artists build skin from large to small: base tone, colour zones, mottling and veins, spots, cavity and pore tint,
roughness, scattering, then displacement from secondary forms down to micro [1][2][3]. Each stage here is one or two
keys of the description; `look_skin(views=["bust"], flat=True)` shows colour without light, the default look the lit
close-ups.

### 0. The person under the skin
Start a new person with the `human` tool: `human("mia", age=3, sex="female")` writes a whole dressed figure (body,
head, eyes, simple clothes, a skin) with that age's MEASURED proportions and size, and returns its body measured
against the references. Children are not small adults, and artists set proportion before anything else [23][24][25]:

| age | stature (median, m / f) | heads tall | sitting height / stature | what reads |
|---|---|---|---|---|
| 1 | 76 / 74 cm | 4.6 | 0.64 | big cranium, no neck from the front, round belly, legs a third of the height |
| 3 | 96 / 95 | 5.4 | 0.58 | belly still leads the profile, shoulders barely wider than the head |
| 7 | 122 / 121 | 6.4 | 0.54 | no waist, long legs coming, a small jaw under full cheeks |
| 11 | 143 / 145 | 7.1-7.3 | 0.52 | girls ahead of boys; adult proportions near, a child's face still |
| 16 | 173 / 163 | 7.9 | 0.52 | adult proportions; the sexes have parted |
| adult | 177 / 163 | 8.0 | 0.52 | |

(Measured children [23][24]; artists' charts round the young ones' heads bigger: 4 heads at 1, 5 at 3, 6 at 5.)
`base.body.age` under 25 gives these by default (MakeHuman's own straight-line blend made a 3-year-old 74 cm and a
16-year-old 1.49 m; `"growth": false` brings that back), `base.body.height` overrides the size, `sex` matters
little under ~10. A head with `follow_body: true` and no `like` keeps its body's own neck: a toddler has almost none.

The chest: `base.body.bust` and `firmness` (0..1, MakeHuman's cup size and firmness targets; 0.5 = the macro shape's
own, which stands 18 mm ahead of the breast bone: an AA cup, small and pointed). The `human` tool gives an adult
woman bust 0.7 (~30 mm, an A/B cup) growing in from 11 to 17 years, firmness falling with age (0.65 at 30, 0.4 at
75) and +0.2 when dressed, which is what a bra does; children and men get none. Judge it by the number the tool
prints (`bust_projection`: ~10-20 mm a flat chest, 30-40 an A/B cup, 50-60 a C/D), not by a clay render alone.
`base.body.nipples: 0` flattens the nipples under cloth with MakeHuman's own nipple targets (then the last nub over
a patch 1.2% of the stature wide; on a child, who has no breast, the small mound under each as well). Never smooth
a wide patch on a woman's chest: 4% of the stature scooped a crater out of each breast, a dented ring in every render.

Figures are dressed by default (`outfit`: tee_shorts, onesie under 2, underwear, none), in cloth with its own volume
(`parts.<p>.garment`: closed over the body's dips, a tube hanging from the chest and belly): a shell of the skin is
body paint, every navel, muscle and nipple prints through it. A baby's onesie goes over a nappy (a blob of bulk
round the seat). Each seed is a different face (`humans.face`: nose, lips, cheeks, chin, jaw, brow, eye size drawn
per person and leaning the way of the age and sex; lids opened to ~0.2 of the pupils' distance; lips together).

Skin can't make a face young, old, male or female on its own: a seven-year-old's skin on an adult's skull is an
adult. On a MakeHuman body with a GNM head, set `base.head.follow_body: true` (or a strength 0..1) when you make the
character: the body's age, sex and weight then shape the head and size it to the body (a child's big cranium and
small jaw, an old man's long heavy lower face). It is off unless you ask, so existing characters keep their heads.
`base.cornea: true` gives the eyeballs a cornea's bulge.
The head then takes MakeHuman's own head shape for that age and sex (a displacement of every vertex), with the
difference between the sexes pushed a little further (`base.head.dimorphism`, 0.8; 0 = MakeHuman's own). Keep the
seed's `spread` at 0.45 or less for women and children: a strong random individuality reads male on a bald head.
`base.head.like: {"age", "sex", "weight"}` sets the head apart from the body.

### 1. Base tone: a pigment model, not a colour picker
`skin(name, {"tone": {"fitzpatrick": 3, "undertone": 0.2}, "age": 35})`
- Skin colour is two pigments: melanin in the epidermis (how dark: 1.3% of its volume in very fair skin to 43% in
  very dark) and haemoglobin in the dermis under it (how red) [4][5]. Real skin tones lie on a curved two-parameter
  surface in RGB, so tinting a base colour by hand gives tones no skin has [6]. `tone` takes `melanin` 0..1 (or
  `fitzpatrick` 1-6), `blood` 0..1, `undertone` (-1 cool/pink .. +1 warm/golden) and computes the albedo; every later
  layer is "this skin with more or less melanin or blood", so cheeks, lips, palms and scars come out right on any tone.
- Very fair skin: Fitzpatrick 1 / melanin under ~0.05 lands in the ITA "very light" bin (individual typology angle
  atan((L*-50)/b*) > 55 deg: L* ~72, b* ~13); F2 is "light" (47), F3 intermediate (37). A rosy fair face is more `blood` (0.5-0.6) with the same low
  melanin, not a negative undertone (that mostly darkens). Judge colour against a photo's FOREHEAD (cheeks flush),
  and check the photo's cast on the sclera (neutral ~R/B 1.0-1.1) before trusting its numbers.
- Albedo stays inside what engines expect of non-metals (sRGB ~50-240) [7]: don't push it darker to "add contrast".
- `age` drives a lot by default (wrinkles, uneven pigment, age spots, veins, drier thinner skin); set it first.

### 2. Colour zones
On by default; strengths in `"zones": {"midface_red": 1.3, "lower_cool": 0}`, all scaled by `"variation"`.
- The face has three bands: a yellower forehead (bone close under the skin, little blood), a red middle (cheeks, nose,
  ears: capillaries), a cooler grey-blue lower third (darker hair under the skin; stronger on men) [8][9].
- Thin skin shows what is under it: purple-blue under the eyes, redder lids. Lips are thin epidermis over a lot of
  blood [10]. Palms and soles have far less melanin (a sharp change on dark skin); knuckles, elbows and knees are
  darker, redder and rougher; fingertips redder; nail beds pink.
- Keep zones subtle. Photographs measure cheeks +1 to +7 a* redder than the forehead; a painted doll has +15.
  Children: rounder, redder cheeks, less everything else.

### 3. Mottling
Blood is never even: blotches of 1-2 cm, redder and paler, plus fine mottle at 3-5 mm; pigment is uneven too, more
with sun and age (`"sun"`). These are the `mottle_*` layers (strength: `variation`). This is what fills the 1.4-11 mm
colour band in the table above; without it skin reads as a spray-painted mannequin.

### 4. Large features: what makes this person
`"features"`: `freckles` (tan macules ~1-3 mm with irregular soft edges, a unique map on the face: where the sun
falls, densest on the nose and the cheeks under the eyes, then forehead; `amount` 1 = ~12/cm2 there, `size`, `clump`
0..1, `dark` share, `zones` weights; shoulders and forearms from a swatch [11]), `moles`
(scattered or placed: `{"at": [{"at": "lm_mouth_corner.L", "offset": [0.01, 0, 0.012]}]}`), `age_spots` (larger,
sharper-edged; default from age x sun), `blemishes` (red papules with a raised shiny centre), `veins` (blue-green,
backs of hands, wrists, temples; raised on old hands), `flush`, `sunburn`, `tan` (give it a `"mask"` to leave tan
lines). Each takes an amount or `{"amount", "where": [zones], "mask": [...], "seed"}`.

`"wrinkles"` default from `age`: forehead lines and crow's feet arrive first (from the late twenties), the "11"
between the brows rarely before 40, nasolabial folds are there at every age and deepen, lines round the lips come in
the fifties [12]; old skin's fine lines deepen into a visible cross-hatch (`crepe`). Set one to 0 to remove it, above
1 to exaggerate, `"amount"` to scale all. They are relief + a darker tint + rougher, not painted grey lines. Deep
folds (nasolabial, jowls) want geometry too: the head's own shape (`base.head`), not paint.

`"scars"`: `cut` and `surgical` (with stitch marks) along a `"path"` of points; `keloid` (raised, smooth, pink-purple);
`burn` and `pockmarks` on a `"zone"` or `"at"` + `"radius"`. `"age"` 0 = fresh (red, swollen) .. 1 = old (paler than
the skin, flat or sunk, slightly shiny). Scar tissue has no pores: the micro relief stops on it [13].

`"tattoos"`: `{"image": {"file": "dragon.png", "at": "elbow.L", "wrap": "cylinder", ...}, "age": 10}` or `"text"`. Ink
sits in the dermis, so it is multiplied INTO the skin's colour under its relief and highlights, never laid on top
like a sticker; with years the lines spread, black drifts blue-green and thins, colours fade [14].

### 4b. Folds the shape does not make (`"folds"`)
`"folds": {"tear_trough": {"amount": 0.8, "roll": 1.3}, "nasolabial": {"amount": 0.8, "L": {"shift": [...], "extent": [0, 0.7]}}, "lid_fold": 0.7}`:
the soft-tissue lines and bulges a GNM head's identity cannot give (eye bags, a deep nasolabial fold, a crisp lid
crease, marionette lines, the groove over the chin, frown lines). Each is a path over the skin from the head's own
landmarks; `shift` (mm across the path at stations along it), `extent` and per-side `amount` are the measured
placement, which `skin_from_reference` fills in from the pictures.
They are GEOMETRY: each fold reshapes the skin's surface itself (a groove, and beside it a roll: the eye bag over a
tear trough, the cheek's pad over a nasolabial fold, the hooding over a lid's crease), so it shows under frontal and
raking light, in profile and in the silhouette, and is in the exported asset (the low poly as far as its triangles
go, the rest in its normal and AO maps). The crease's tint and shade stay colour, from the same parameters.
Per fold: `amount` 0..1.5, `width` (mm, the groove), `depth` and `roll` (0..3, x the feature's own: `roll` is the bag
/ pad / the skin over a lid's crease), per side `L` / `R`: `amount`, `shift`, `extent`. mm at amount 1: nasolabial
groove 0.4 / pad 1.3, marionette 0.3 / jowl pad 0.5 (a soft 6 mm fold from the mouth's corner down and a little out),
commissure 0.45 (the depression at the mouth's corner), tear_trough 0.6 / bag 1.4, lid_fold crease 0.85 / roll 0.6,
mentolabial 0.8, glabella 0.35, mouth_corner 0.3 (the crease running out from the corner). A heavy bag:
`"tear_trough": {"amount": 1.2, "roll": 1.6}`.
The upper lid: `"lid_fold": {"amount": 1, "hood": 0.8}`: `hood` (0..1.5, lid_fold only) is HOODING: over the outer
half the fold's line comes down toward the lashes (1.7 mm at 1), the roll over it stands 1 + 1.6 x hood higher and
reaches nearer the lid's margin; `roll` thickens the skin over the whole crease. Where the lid lies thin over the
eyeball the crease cannot go in: it takes the room there is and the rest of its depth stands out as the fold's own
lip just over the line (the eyeball is a constraint, not a stop: the crease stays one line from corner to corner).
Its dark line is calibrated on a photograph: amount 1 renders as dark as a clear photographed crease (read the same
way, 0.32). The nasolabial path follows the HEAD'S OWN crease where the shape has one (a middle-aged GNM head does),
else it runs from the nose's wing at 30-40 deg from the vertical, 12-15 mm outside the mouth's corner.
`"chin_notch": 0.8`: the chin's midline notch / cleft with a soft lobe each side (0.9 mm deep, lobes 0.6 at amount 1;
`roll` = the lobes). `commissure` and `chin_notch` are NOT READ by skin_from_reference (the mouth's own corner
shadow / the chin's own shading lie in their windows: the reply says so): set them by eye.
FOLDS UNDER EXPRESSION (export_asset(face_shapes=...)): a fold laid in the neutral would ride a face shape rigidly (a
crease across a closed lid). Each fold has a gain per ARKit shape (`skin_folds.EXPRESSION`: lid_fold eyeBlink 0,
eyeWide 1.3, eyeSquint 0.5, browDown 1.2; tear_trough eyeSquint / cheekSquint 1.4; nasolabial mouthSmile 1.5,
cheekSquint 1.2, jawOpen 0.8; marionette jawOpen 0.6, mouthFrown 1.4; glabella browDown 1.6 ...; first guesses),
and the export bakes (gain - 1) x the fold's own displacement into that shape's morph target (the report's
`fold_expressions`: mm per fold and shape). GEOMETRY ONLY: the fold's normal map and its painted line are one
texture for all shapes and stay (a GLB's morph targets carry POSITION and vertex NORMAL, no per-target texture):
fading them with a shape needs a wrinkle-map blend in the engine. `"fold_expressions": false` leaves the folds rigid.
The displacement fades out before the lid margins and the lips and never reaches the eyeball; with no
folds nothing is built or evaluated. `"fold_relief": "paint"` keeps the older painted relief (bump only).
Look at them with `look_skin` under two lights; a fold is a few voxels wide: judge close-ups, not the bust.

### 5. Hair on the skin
`"hair"`: `brows` are hairs, not a painted arc: a drawn picture of ~900 tapered hairs that grow up at the inner end,
along the brow in the middle and out-and-down at the tail (`density`, `thickness`, `color`, `grey`; `taper` thins the
tail more, `tail` shortens it: a thick dense brow with a clean thin tail is thickness 1.3-1.5 + taper 0.92), laid from the brow
landmarks; `lashes` darken the lid margins (the skin touching the eyeball); `stubble` is a unique map of cut hairs
on the head's own surface (no tiling) plus the shadow of the hair in the skin, by `style`: `clean` (a faint cool
shave shadow), `five_oclock`, `short` (1-3 days), `designer` (trimmed ~4 mm: crisp cheek line and neckline),
`heavy`, `patchy`; `grey` = share of white hairs (salt and pepper); `cheeks` (how far the cheeks fill), `cheek_line`
/ `neckline` (move the lines, interoculars), `trim` (0 grown out: the density tapers over ~2 cm with stragglers;
1 a razor line), `patchy`, `length`, `color`. Hair grows down, out from the philtrum, toward the throat under the
chin; the moustache, chin and jaw are full, the cheek's rounded front and the mouth's corners thinner. Real beards
have no edge unless trimmed: match the fade on your reference before the colour.
`body` is fine hairs on forearms and chest; `scalp` is a shaved or cropped head (`amount`, `color`, `hairline` 0..1:
how far it comes down the forehead): the shadow of the hair under the skin plus cut hairs, so a head without a groom
isn't a mannequin. Long lashes, beards and head hair are geometry (`groom_hair`).

`"eyes"` (on by default when the body has eyeballs): `iris` colour, `iris_size` (unset on a GNM head: GNM's limbus for the identity), `pupil` (unset: GNM's pupil, base.head.expression.pupils_000), `veins`, `sclera`. The iris
is fibres running out from the pupil with a paler collarette and a dark limbal ring, the white is never white (pinker
toward the corners, a few vessels), the upper lid shades the top of the eye, and the inner corner has a pink wet
caruncle. A flat coloured disc with a black dot is the toy-eye tell.

**Only part of it** (`"only": [groups]`): a character whose skin is already painted by hand can take just some groups
of the description and nothing else: `"eyes"` (the painted eyeballs), `"eye_rims"` (caruncle and waterline),
`"zones"`, `"lips"`, `"roughness"`, `"micro"`, `"features"`, `"shading"` (the skin part's base colour, roughness,
scattering and coat). `skin(name, {"only": ["eyes"], "eyes": {"iris": "#56666e"}})` gives him the irises and leaves
his skin, its paint and its shading exactly as they are (delete his old flat iris / pupil paint layers so the picture
shows). Without `"shading"` the layers are ordinary paint layers under the model's own.

### 6. Micro detail: tiling, never painted per character
The skin's microrelief is polygonal plateaus between furrows (primary lines 20-100 um deep, the only ones the eye
sees) with pores at crossings; facial pores are 0.2-0.5 mm across, 10-90 per cm2 [15][16]. No unique texture can hold
that for a whole body, so, as in game pipelines, the unique maps carry wrinkles and colour and a small TILING detail
map carries pores [2]: generated swatches (`pores` on the face, `lines` on the body, `coarse` on knuckles/elbows/old
skin, `lips`) laid as relief with darker, rougher furrows ("cavity": pores catch no light [3]). `"detail"` scales it;
children have much less. Judge it in `look_skin(views=["cheek"])`, not at bust distance: at 60 cm it should only
break the highlight up.

### 7. Roughness and the highlight
Skin's reflectance is IOR ~1.4: F0 0.028, lower than the 0.04 default [17]. Measured roughness varies little across a
face but systematically: nose and forehead smoother (sebum), chin, beard and upper lip rougher, lips smooth and wet
[18]. `"oil"` moves the T-zone and adds a second, tighter lobe over the broad one (real skin has both [19]); never
leave one flat roughness. A highlight that is one clean blob is the plastic tell: `look_skin` reports its breakup.

### 8. Cosmetics, in the order they go on
`"makeup": {"look": "natural" | "everyday" | "evening", ...items override the look}`: the looks are a make-up artist's
sets ("natural" = the no-make-up make-up: a sheer base, a little concealer, brushed brows, mascara, a tinted balm).
Placement follows the artists' rules on each side's own landmarks: blush on the apples swept toward the temple
(`place`: apples / lifted / draped), contour in the hollow under the cheekbone stopping under the outer eye, liner
along the lash line thickening outward with a `wing` that continues the lower lash line toward the brow's tail,
shadow on the lid with a deeper `crease` and an `outer` V, lipstick to the vermilion border (`liner`, `overline`).
`foundation` evens zones, mottling and spots toward one tone and sets the finish (`matte` rougher,
`dewy` smoother) [20]; `concealer`; `contour` (darker under the cheekbones, jaw, nose sides); `blush`; `highlight`
(paler AND smoother on the cheekbone tops, nose bridge, cupid's bow); `eyeshadow` (`matte`, `shimmer`, `metallic`);
`eyeliner` (`wing`); `mascara`; `brows`; `lipstick` (`matte` / `satin` / `gloss`: the finish is most of the look);
`nails`. Every product changes roughness and specular, not only colour; the skin's pores stay on top of all of it.

### 9. Shading check
- `look_skin` renders in EEVEE: seconds a view once the material is compiled (a skin edit costs 20-150 s, more with
  many scars, tattoos and make-up). `engine="cycles"` path-traces instead (real subsurface scattering: use it for this
  check); a skin with very many fine layers can exceed what Cycles' shader holds and renders BLACK: thin it out.
- `look_skin(views=["face", "ear"])`: under the studio light the shadow edge should turn redder, not grey; back-lit,
  ears and nostril wings should glow. `"shading"`: `subsurface` weight, `radius` per channel (red travels 2-3x
  further than green and blue [18]), `scale` (m). Too much scattering reads as wax, especially on hands [21].
- Stylised characters: a style sheet can sit on top (`variation` and `detail` down to 0.3-0.5, features off): the
  same skin, simplified, rather than a flat fill.
- Export: the unique maps carry colour, roughness and the relief down to the texel; the tiling pore detail is
  exported beside them with a recipe (see export_asset). glTF has no ratified subsurface extension yet
  (KHR_materials_diffuse_transmission is a release candidate; KHR_materials_subsurface a draft) [22]: engines get the
  scattering numbers in the material's extras for their own skin shader (Unreal's Subsurface Profile, Unity HDRP's
  Diffusion Profile).

## What goes wrong
- Zones or mottling visible as shapes at bust distance: `variation` too high. Compare the a* row to the photographs'.
- Freckles like a rash: lower the amount before the size; real ones cluster and vary in strength.
- Wrinkles on a 25-year-old: `"wrinkles": {"amount": 0.3}`; an 80-year-old without crepe reads 50.
- Grey lips on dark skin, or orange ones on fair skin: don't recolour them; change `lips.blood` / `lips.melanin`.
- A tattoo that looks printed: it is probably a paint layer on top; use `tattoos` (multiplied, aged).
- Make-up that looks like paint: check its finish; foundation without `variation` left in it is a mask.

## Sources
[1] TexturingXYZ multichannel displacement workflow (secondary / tertiary / micro channels): sefki_i.artstation.com/blog/vzvG
[2] Epic, "Creating Human Skin": dev.epicgames.com/documentation/unreal-engine/creating-human-skin-in-unreal-engine
[3] 3D Scan Store, skin shading in Marmoset Toolbag (cavity, detail weight): 3dscanstore.com/blog/skin-shading-in-marmoset-toolbag
[4] S. Jacques, "Skin Optics": omlc.org/news/jan98/skinoptics.html
[5] Donner & Jensen 2006, "A Spectral BSSRDF for Shading Human Skin": cseweb.ucsd.edu/~henrik/papers/skin_bssrdf/ ; Jimenez et al. 2010: iryoku.com/skincolor/
[6] Alotaibi & Smith 2017, "A Biophysical 3D Morphable Model of Face Appearance" (ICCV workshops)
[7] PBR albedo chart: shinsoj.artstation.com/blog/Q9j6
[8] polycount.com/discussion/149063/color-temperature-of-skins
[9] 3dreference.notion.site/Human-Face-Color-Zones-fdf70717d6974ca6a08660cce9fa1294
[10] Aliaga et al. 2022, "Estimation of Spectral Biophysical Skin Properties from Captured RGB Albedo": arxiv.org/abs/2201.10695
[11] DermNet, brown spots and freckles: dermnetnz.org/topics/brown-spots-and-freckles
[12] Review of facial creases: researchonline.ljmu.ac.uk/id/eprint/6404/
[13] Acne scar types: healthline.com/health/skin-disorders/types-of-acne-scars
[14] Tattoo ageing: storiesandink.com/en-us/blogs/journal/why-black-tattoos-turn-grey-the-science-of-tattoo-ageing
[15] Skin microrelief: pmc.ncbi.nlm.nih.gov/articles/PMC9838641
[16] Facial pores across populations: pmc.ncbi.nlm.nih.gov/articles/PMC4337418
[17] GPU Gems 3, ch. 14, "Advanced Techniques for Realistic Real-Time Skin Rendering"
[18] Weyrich et al. 2006, "Analysis of Human Faces using a Measurement-Based Skin Reflectance Model"
[19] Unreal Subsurface Profile (dual specular lobes 0.75 / 1.3, mix 0.85): dev.epicgames.com/documentation/unreal-engine/using-a-subsurface-profile-in-your-unreal-engine-materials
[20] MetaHuman makeup material controls: dev.epicgames.com/documentation/metahuman/makeup-material-controls
[21] nofilmschool.com/cgi-skin
[22] Khronos glTF extension registry: github.com/KhronosGroup/glTF/blob/main/extensions/README.md
[23] WHO Child Growth Standards (0-5 y) and growth reference (5-19 y): who.int/tools/child-growth-standards
[24] Snyder et al. 1977, "Anthropometry of Infants, Children and Youths to Age 18" (UMTRI-77-17; tables at math.nist.gov/~SRessler/anthrokids)
[25] Loomis, "Figure Drawing for All It's Worth" (1943): proportion charts by age (heads tall, the midpoint)
