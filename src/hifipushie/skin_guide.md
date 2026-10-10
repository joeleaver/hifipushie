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

### 5. Hair on the skin
`"hair"`: `brows` are hairs, not a painted arc: a drawn picture of ~900 tapered hairs that grow up at the inner end,
along the brow in the middle and out-and-down at the tail (`density`, `thickness`, `color`, `grey`), laid from the brow
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

`"eyes"` (on by default when the body has eyeballs): `iris` colour, `iris_size`, `pupil`, `veins`, `sclera`. The iris
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

## Tool reference

The full documentation of this topic's tools: their MCP descriptions are the short form. guide(topic="<tool name>") returns one section. These tools are the `human` toolset: enable_toolset("human") turns it on.

### `skin`

`skin(name, skin=None, replace=False, note='')`

Describe a human's skin (spec["skin"]) and save it: the description expands into ordinary paint layers
("skin:<layer>", under the model's own paint) and the skin part's shading. guide(topic="skin") is the artist's
workflow in stages; skin_reference lists every key, default and zone. For a model built on a `base` (MakeHuman /
template body, GNM head): zones are placed from its joints and lm_* face landmarks.
skin: a patch merged into the stored description (objects key by key, null deletes; replace=True starts over):
  {"tone": {"fitzpatrick": 1..6 | "melanin": 0..1, "blood": 0..1, "undertone": -1 cool .. 1 warm},
   "age": years, "variation": 1, "detail": 1, "oil": 0..1, "thin": 0..1, "sun": 0..1,
   "features": {"freckles": 0.6, "moles": {"at": [...]}, "age_spots", "blemishes", "veins", "flush", "sunburn",
                "tan": {"amount", "mask": [...]}},
   "wrinkles": {"amount": 1, "forehead": ..., "crows_feet": ...},          (default: from age)
   "hair": {"brows": {"color", "density", "thickness"}, "lashes", "stubble": 0.7, "body": 0.5},
   "scars": [{"kind": "cut" | "surgical" | "keloid" | "burn" | "pockmarks", "path": [points] | "zone": name, "age": 0..1}],
   "tattoos": [{"image": {"file" | "text": {...}, "at", "size", "dir", "wrap"}, "age": years}],
   "makeup": {"foundation": {"amount", "finish"}, "blush", "contour", "highlight", "eyeshadow": {"color", "finish"},
              "eyeliner": {"wing"}, "mascara", "brows", "lipstick": {"color", "finish": "matte" | "satin" | "gloss"}, "nails"},
   "zones": {built-in zone layer: strength}, "lips": {...}, "shading": {...}, "part": "body",
   "only": ["eyes"]}   only these groups are laid and nothing else: "eyes" (the painted eyeballs), "eye_rims",
                       "zones", "lips", "roughness", "micro", "features", "shading" (the part's base colour and
                       scattering). ["eyes"] puts the skin tool's irises on a character whose skin is painted by
                       hand, and leaves that skin and its shading alone.
Any layer of the model's own paint can use the same anatomy: {"zone": "cheekbone.L"} in edit_model paint ops.
Then look_skin (fast cropped close-ups + measurements), or sync + look for the whole model.
Returns the tone's colours and the layers the description made.

### `look_skin`

`look_skin(name, views=None, size=768, light=None, flat=False, layer=None, engine='eevee', save=None)`

Close looks at the skin, fast: bare-skin crops of the model (head and shoulders; forearm and hand: without
clothes or hair, ~1 mm mesh, kept between calls) rendered under fixed lights, with measurements of the face next
to what photographs of real skin measure (contrast per feature size in lightness and colour, colour zones,
highlight size and breakup, micro contrast) and hints. The first look of a region meshes it (~2 min); after a
skin or paint edit ~20-40 s.
views: any of bust, face, three_quarter, side, cheek (macro), eye, mouth, forehead, ear (back-lit: light through
the ear), hand, palm, forearm (default face, three_quarter, cheek, eye, mouth, ear).
light: "studio" (a key from the model's right + a weak fill), "soft" (broad frontal: colour without highlights),
"back" (back-lit); default per view. flat=True: the unlit colour. layer: one layer's mask, orange on grey clay
("freckles" = "skin:freckles"; or any paint layer's name).
engine: "eevee" (fast) or "cycles" (path traced, slower: real subsurface scattering: the shading check for
shadow edges and back-lit ears).
Judge in this order: flat colour at bust distance (tone, zones), then the lit bust, then the close-ups.

### `skin_reference`

`skin_reference()`

Everything the `skin` description takes: the anatomical zones (also usable by any paint layer as
{"zone": name}), the tone model, features, wrinkles, hair, scars, tattoos and make-up with their keys and
defaults.
