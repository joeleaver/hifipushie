# Skin: texturing a human the way character artists do

Tools: `skin` (describe the skin), `look_skin` (fast close-ups + measurements), `skin_reference` (every key, default
and zone), and the ordinary paint tools (`edit_model` paint ops can address the same anatomy with `{"zone": name}`).
The description `spec["skin"]` expands into ordinary paint layers named `skin:<layer>` laid UNDER the model's own
paint, plus the skin part's shading. It needs a model on a `base` (a MakeHuman or template body for the hand, arm and
leg joints; a GNM head for the face's `lm_*` landmarks).

## Why CG skin reads as plastic (measured, 13 photographs vs our old flat-colour skin)

| what a photograph has | photographs | one colour + one roughness |
|---|---|---|
| lightness contrast at 0.35-1.4 mm (pores, skin lines, their highlights) | 0.8-1.3 L* | 0.04-0.08 |
| colour (a*) contrast at 1.4-11 mm (mottling, freckles, redness) | 0.4-0.6 | 0.04-0.11 |
| a highlight | 5-13% of a cheek or forehead, broken into 1-10 mm pieces | none |
| cheeks and nose redder than the forehead | a* +1 to +7 | +0.3 |

In order of how much they matter: (1) no fine relief, so no broken-up highlight; (2) one albedo colour: no zones, no
mottling; (3) no visible specular at all (uniform high roughness, one lobe); (4) no red in the shadow edge and no
light through thin parts; (5) lips, brows and eye area painted as flat shapes. `look_skin` prints the same numbers for
your model next to the photographs'.

## The stages (do them in this order; look after each)

Artists build skin from large to small: base tone, colour zones, mottling and veins, spots, cavity and pore tint,
roughness, scattering, then displacement from secondary forms down to micro [1][2][3]. Each stage here is one or two
keys of the description; `look_skin(views=["bust"], flat=True)` shows colour without light, the default look the lit
close-ups.

### 1. Base tone: a pigment model, not a colour picker
`skin(name, {"tone": {"fitzpatrick": 3, "undertone": 0.2}, "age": 35})`
- Skin colour is two pigments: melanin in the epidermis (how dark: 1.3% of its volume in very fair skin to 43% in
  very dark) and haemoglobin in the dermis under it (how red) [4][5]. Real skin tones lie on a curved two-parameter
  surface in RGB, so tinting a base colour by hand gives tones no skin has [6]. `tone` takes `melanin` 0..1 (or
  `fitzpatrick` 1-6), `blood` 0..1, `undertone` (-1 cool/pink .. +1 warm/golden) and computes the albedo; every later
  layer is "this skin with more or less melanin or blood", so cheeks, lips, palms and scars come out right on any tone.
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
`"features"`: `freckles` (tan spots under 3 mm, clustered on nose and cheeks, shoulders, forearms [11]), `moles`
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

### 5. Hair on the skin
`"hair"`: `brows` are hairs, not a painted arc: a drawn picture of ~900 tapered hairs that grow up at the inner end,
along the brow in the middle and out-and-down at the tail (`density`, `thickness`, `color`, `grey`), laid from the brow
landmarks; `lashes` darken the lid margins (the skin touching the eyeball); `stubble` is
a cool shadow under the skin (dark hair seen through it) plus dots, full on chin and lip and thinning up the cheek;
`body` is fine hairs on forearms and chest; `scalp` is a shaved or cropped head (`amount`, `color`, `hairline` 0..1:
how far it comes down the forehead): the shadow of the hair under the skin plus cut hairs, so a head without a groom
isn't a mannequin. Long lashes, beards and head hair are geometry (`groom_hair`).

`"eyes"` (on by default when the body has eyeballs): `iris` colour, `iris_size`, `pupil`, `veins`, `sclera`. The iris
is fibres running out from the pupil with a paler collarette and a dark limbal ring, the white is never white (pinker
toward the corners, a few vessels), the upper lid shades the top of the eye, and the inner corner has a pink wet
caruncle. A flat coloured disc with a black dot is the toy-eye tell.

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
`"makeup"`: `foundation` evens zones, mottling and spots toward one tone and sets the finish (`matte` rougher,
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
