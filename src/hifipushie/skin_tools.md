# Skin: tool reference

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
"back" (back-lit), "rake" (a low light from the side: what shows relief: folds, bags, a lid's crease), "photo" (the front
reference's own fitted light AT THE PICTURE'S EXPOSURE, as the last skin_from_reference read measured it: the light to
judge tone beside the reference; a render 10 L under its reference reads as a tan whatever the albedo); default per view. flat=True: the unlit colour. layer: one layer's mask, orange on grey clay
("freckles" = "skin:freckles"; or any paint layer's name).
engine: "eevee" (fast) or "cycles" (path traced, slower: real subsurface scattering: the shading check for
shadow edges and back-lit ears).
Judge in this order: flat colour at bust distance (tone, zones), then the lit bust, then the close-ups.

### `skin_from_reference`

`skin_from_reference(name, out='', groups=None, rounds=2, read_only=False, stubble=None, anchor='auto', tone=None, white=None, project=False, layers=True)`

WITH A DE-LIT ATLAS (the default route for photographs of a person): `project=True` first runs skin_project as a
MEASUREMENT (the atlas, its confidence and each view's fitted light colour are stored on the model; its colour layer
stays off), the read then takes the atlas as its picture (one albedo for every view, light and shading already out;
ours = our albedo at the same surface points: no stage, no render; the irises and the folds are not read this way),
and `layers=True` stores the skin's colour as a STACK OF LAYER MAPS decomposed from the atlas (`skin.stack`,
skin_layers.py): in optical density the atlas is split per texel into melanin, haemoglobin (the two chromophores of
Tsumura et al. 1999 / 2003; the axes are OUR pigment model's own colours for melanin and blood at the model's tone,
and the reply says how far the data's own ICA axes lie from them) and a neutral darkness; from these, in order, each
cause takes its own map inside its own support at its own scale: pigment (4 mm), redness (2.5 mm), periorbital
(dark circles, lid colour: 1.2 mm), brows (the skin-level darkness under the brow hairs: 0.7 mm, laid at 0.4), lips
(inside the vermilion, whose edge is the picture's own colour edge: 0.8 mm), beard (stubble shadow: 2 mm; our
stubble then keeps its hairs and loses its own shadow), shade (dark with no pigment colour and no layer: 3 mm), plus a
freckle DENSITY map that confines the freckle generator. Each map is a multiply layer `skin:stack_<name>` over the
base (the lightest skin), filled where no picture saw: mirror image, then the layer's own neighbourhood, then its
mean (a provenance image marks measured / mirrored / inferred). The reply gives the RECOMPOSITION's error against the
atlas by zone and band: what the stack does not carry is the fine band (our generators' job) and the residual.
Editing one cause = one layer's strength (skin_layers.edit: blush, pale, tan, older, no_stubble, rested, tired). The
export bakes the stack like any paint. The photo's pixels do not ship; the decomposition does.
EYE FORMS AND THE BAKE: the head's forms come first (base.head.lid_fold with its crease tail, head.shape
eye_bag / cheek_flat), THEN the atlas is projected on that head (its de-lighting sees their shading, so the photo's crease
and bag shadow are not taken as pigment), then the stack. The stack carries a baked OCCLUSION (ambient occlusion x a
cavity term from the final geometry, floor 0.55: EEVEE and game lights lose a lid fold's occlusion) and a CREASE LINE (the
fold's platform under the hood + the roll's edge + the tail), each with a strength measured against the photo. The crease
line and the lid's share of the occlusion fade with the pose's lid close in looks, and the export ships them OUT of
basecolor as <atlas>_blink_multiply.png: shade basecolor x lerp(1, map, 1 - eyeBlink) (a blink-driven wrinkle map).
An export of a full human head with these maps needs ~15-20 GB: under the machine's 12 GB job cap it is killed (exit 137);
run it with CAP=20G (bin/capped). The lid fold's vertices keep their built positions in the export's wrap (the field
would collapse the hood); the bake's rays inside the fold's slit still pick up speckle on the upper lid (open).

WITHOUT an atlas (paintings, a model with no projection): the per-picture read below.

The reference pictures as a MEASUREMENT of the skin: the description (spec["skin"]) is set from what the fitted
references show, and the result is the ordinary procedural skin (clean under any light, from any angle). The picture
is never the albedo (that is texture_from_reference: it bakes the picture's light, brushwork and hair, and seams where
no camera looked). Needs fitted references (human_reference / a block-in) and a head whose SHAPE is already accepted:
every read lies where the model's own landmarks put it.

How it measures (differential): per view, the picture P, OUR dressed head R through the same camera under the
picture's own fitted light, and our albedo A at every pixel's surface point; the picture's albedo is A x P / R, so
light, shading and scattering cancel as far as our head and light stand in for theirs. Region colours are read
against the face's own plain skin (exposure and white balance cancel); folds are valleys of luminance across a
landmark path, the picture's against ours at the same place.

What it reads and sets (groups; default all):
- `tone`: melanin / blood / undertone. A picture does not say how LIGHT a skin is (exposure x albedo), so lightness
  has an anchor, in this order: (1) the PRIOR: the model's stated `skin.tone` (set it first, or pass `tone=` a
  Fitzpatrick type 1..6 or skin.tone's own keys); the pictures then correct hue and saturation only and the plain
  skin's lightness stays within 3 L* of the prior and its colour within 5 (a*b*: a backdrop is a weak white balance);
  the WHOLE FACE's mean albedo (every skin zone, stubble apart) is held to the same bounds, and no zone's offset from
  that mean may leave the prior's by more than 4 L* / 5 a*b* (the zone layers are scaled back, and the reply says so).
  (2) a KNOWN WHITE in the picture: clothing under the face, searched in the WHOLE picture (the parser's cloth:
  bright, neutral, 250+ px, brighter than the lit skin and no darker than 0.8 x a neutral backdrop: a pale grey shirt
  is refused, and the reply says why), or one you point at: `white=[{"view": i, "box": [x0, y0, x1, y1] (picture
  pixels), "albedo": 0.8}]` (paper, a shirt, a white wall: taken at your word). Skin albedo = its albedo x lit skin /
  white, which may move the lightness up to 8 L* off the prior (that the white is lit as the face is INFERRED). A
  backdrop is NOT an exposure anchor (its albedo and its own light are unknown): white balance only. The reply says
  which was used and the plain skin's and whole face's Lab before -> after. With no neutral backdrop and no white the
  tone is NOT READ (everything else still is). The sclera is never an anchor (lid and lash shadow).
  anchor="prior" ignores a white.
- SHADE IS NOT PIGMENT: a region the pictures show darker than our render under the fitted light predicts is taken
  first as shade our head does not cast (deeper-set eyes, the jaw turning from a light the fit only roughly knows),
  in the pictures' own measured shade colour (darker and warmer: about r 0.8 / g 1.05 / b 1.3 as exponents on
  photographs), and is NOT painted in; the reply lists those regions and their L*. What is left to the zone tints is
  colour off that line (redder, bluer, greyer) and, where a beard may be, its shadow. A real tan line or dark circles:
  set that zone's strength yourself. A parameter whose move is worth next to nothing to the fit is put back.
- the reply's views state the picture's exposure against our render under its fitted light (EV); `look_skin(light=
  "photo")` renders at it.
- `zones`: skin.zones forehead_yellow, midface_red, nose_red, perioral_red, lower_cool + features.flush.
- `eyes`: zones under_eye, eyelids, periorbital (the socket's own darker, browner skin). These three overlap: judge
  the region's colour, not each number.
- `lips` (their colour is read like a zone; check it in the reply's AFTER table, lip_upper / lip_lower d, and by eye
  under light="photo"): lips.blood / melanin (x the TONE's melanin: a dark lip on a very fair tone needs 10-20) , lips.strength (how much of
  the vermilion is the lips' own colour: a man's is 0.65 of a woman's by default) and lips.lower {blood, melanin}. The vermilion's own
  gradient (darker toward the wet line and the corners, a lighter lower-lip body: `lips.gradient`, 0..2.5, default 1)
  and its border's softness (`lips.border`, mm, default 1.5) are NOT read: set them by eye.
- `stubble`: hair.stubble's `zones` {moustache, chin, soul_patch, jaw, cheeks, neck} and density, from the lower
  face's shadow zone by zone; a beard is ADDED to a face without one only if skin.sex is not female (or stubble=True),
  and taken off where the pictures show none.
- `brows`: hair colour and density from the band's darkness; the band's placement and thickness by brow_read's fit.
- `freckles`: dark specks per cm2 on cheeks, nose and forehead against ours (needs 0.5 mm a pixel or finer); 0 when
  the pictures show none.
- `eyeballs` (in the default groups): `eyes.iris` from the picture's OWN iris (the limbus found on the
  picture; the ring's middle tones along its lateral rays: no catchlight, no lid) against the BRIGHT part of the sclera
  just outside it, over the same ratio in our render; front and 3/4 views with an iris of 10 px radius or more. The hue
  is never clipped per channel. INFERRED (the sclera is taken as ours): check it against the picture. "NOT READ" in the
  changes = the colour was left alone: set `skin.eyes.iris` by hand.
- `folds`: the CHECKLIST of soft-tissue features the shape model does not make: nasolabial, marionette, commissure,
  mouth_corner, mentolabial, tear_trough (its roll is the eye bag), lid_fold (the upper lid's crease as a line), glabella, each
  PRESENT / absent / "ours has more" per side with strength, extent along its path, placement (mm across the path)
  and a confidence; and the fields of fine lines (forehead, crow's feet, under the eye, round the lips) as energy over
  the cheek's. Each feature states the picture resolution it needs and answers "cannot tell" below it (a face 110 px
  wide: 1.4 mm a pixel reads the broad folds, never a lid crease or fine lines). Three detectors: a VALLEY of
  luminance across the path; a lit / shaded STEP across it with the fitted light's sign (a side-lit fold, a painter's
  nasolabial under a lamp: no valley); and, for the upper lid, the fold line searched up from the PICTURE's own lash
  line (which places the crease: mm over the lashes per column, turned into millimetres along the leaning lid; its
  strength is the line's darkness against OUR rendered crease's, read the same way at the same scale, so a second
  round closes on it). They are laid by skin.folds as GEOMETRY (section 4b) with their tint and shade as colour.
  SYMMETRY IS THE PRIOR where a side cannot be read: tear troughs / bags, nasolabial and marionette folds come in
  pairs; when one side reads with confidence and the other is not seen, or the pictures are too coarse to place a
  fold (0.7 mm a pixel or more: there "not found" is no evidence), the unread side takes the read side's amount and
  the reply says INFERRED from the other side. On finer pictures a side that reads absent stays absent. A soft fold
  is never laid shorter than 65 % of its path (a marionette nick reads as a scar).

rounds: read -> fit -> re-render -> read again; the second round corrects what the first could only estimate
(densities, fold strength and placement). ~3-5 min a round on a head. read_only=True returns the read (tables per
region and per fold) without changing anything: use it to see what the pictures say before deciding.
The reply is the side-effect report: every parameter changed, from -> to, and the read behind it; parameters "at its
bound" say the picture asks for more than that control gives.
What it does NOT read: roughness / oil / pores, fine lines (reported as energy, never fitted: they follow the light),
anything under hair, make-up as such (a dark lid reads as periorbital skin), the tone's lightness without an anchor
(the prior holds it), the lips' gradient, and whatever the shape gets wrong (a fold the head's geometry already has is
"as ours"). Fold STRENGTH is good to about a third (a valley's depth follows the light), presence and side are solid;
placement of the horizontal grooves is biased toward the wall the light misses in round 1 and corrected in round 2
(ours against the picture's), so run 2+ rounds.

### `skin_project`

`skin_project(name, out='', views=None, remove=False, report_only=False, delight=True, ears=False, mirror=True, tone='model', opacity=0.0, detail_depth=0.00012, parse='mediapipe', eyes=False, stubble='picture')`

The fitted reference pictures as a de-lit ATLAS in the head's own texture space: the MEASUREMENT skin_from_reference
fits the skin to (its layer stack). By default nothing of the photograph is laid as colour (`opacity=0`); `opacity=1`
is the explicit "photo skin" mode (the de-lit picture itself as the colour: the ceiling, a judging overlay). Each picture is
projected through its fitted camera into the head's own texture space (the one human mesh's atlas, ~0.2 mm a texel),
de-lit into albedo, blended, the unseen filled, and saved as `skin.projection` = {albedo, detail, box, opacity,
detail_depth, head}: two images the skin lays as layers `skin:projection` (colour, over the skin's own colours and
painted hair, under scars / tattoos / make-up) and `skin:projection_detail` (fine relief). Relief, roughness,
scattering, eyes, strands and the lid margins (wet line, caruncle, lash roots) stay the procedural skin's. export_asset
bakes it like any paint. Needs a one-mesh head with fitted references and an ACCEPTED shape: the pictures land where
the model's surface is. After the head's shape changes, run it again (the layer stores the head's key).

Use it when the references are photographs of the person and likeness matters more than a clean procedural skin: the
face's own pigment, brows, stubble shadow, lines and asymmetries come with it. Not for paintings (brushwork lands on
the skin) and not as a way round a wrong shape (a misplaced feature is painted where the picture has it, with no
form under it).

Steps, and what each cannot know (the reply reports all of it per model):
- PROJECT: per texel and picture the colour, facing angle and a confidence (seen, square-on, unclipped, lit).
- EXCLUDE: the picture's hair, loose hairs near it, clothing and backdrop (the picture's own parse: `parse`
  "mediapipe", Apache 2.0, decides what ships; "" = a colour rule; "bisenet" is trained on non-commercial data and is
  a measuring tool only: do not ship a texture cut with it); the lid margins (a band that grows with the lids'
  measured misfit); ears (`ears=False`: left to the procedural skin; True: projected only where the picture's ear
  lands on the model's, else left out and said so); skin at a grazing angle.
- DE-LIGHT (`delight`): picture = albedo x shading; the shading is what THIS head's geometry does under a
  low-frequency light (order-2 SH through each texel's own visibility: occlusion and soft self-shadow included) plus
  one soft key light with its cast shadow when the fit finds one, per picture and colour channel, fitted on the
  plain skin and re-fitted against the views' agreed albedo. What the fit explains goes; pigment and fine lines stay.
  So does the shading of forms the head does not have (a bag's shadow, a fold's dark side): reported per region as
  "dark the light does not explain" (neutral = shadow-like, coloured = pigment-like). Those folds need FORM, not paint.
- `tone`: "model" = the projected plain skin takes the model's own `skin.tone` (exposure and white balance are the
  model's: set the tone first, by hand or skin_from_reference); "picture" = the picture's colour, only its lightness
  the model's.
- BLEND in two bands (broad colour by confidence, fine detail from the best view).
- FILL: the mirror image where only the other side was seen (`mirror`; INFERRED), small holes from the skin round
  them, then the procedural skin retoned to the projected skin at the border with fine texture of its statistics.
  Scalp, nape, under-chin and ears are normally ours.
- DETAIL: grooves from the albedo's fine dark LINES where the picture is trusted and their directions agree (wrinkle
  bundles; not hairs, specks, freckles), `detail_depth` m deep.

- EYES: the eyeballs are never pasted. The irises are READ in the views within 35 deg of the front (a radial
  profile inside the sectors the lids leave open, 22 deg either side of horizontal, catchlights left out) and always
  reported; `eyes=True` sets `skin.eyes.iris` (the iris' body) from it (off by default: on a hooded eye a wider
  sector read lid skin and turned a grey iris brown; judge the read beside the photograph first), as albedo through the gain of the skin under the eye (INFERRED: the eye lit as that skin; on the
  synthetic head the read returned the true colour within 1 dE). The limbal ring's darkness and the colour round the
  pupil are reported, not set (the read is not calibrated to the parameter).

`out`: save to a copy (references and cameras copied). `report_only`: the report without saving. `remove`: take the
projection out. `views`: which reference views to use. Files (albedo, raw = not de-lit, detail, confidence: red
picture / green mirrored / blue ours, report) go to `<model>/skin_projection/`.
Stubble: the picture carries its own beard shadow, so `stubble="picture"` (default) removes `skin.hair.stubble` from
the saved model and says so; "keep" keeps ours on top (one or the other is the rule). Judge beside the photographs under the photo's light AND a new side light, from angles no picture has.

### `skin_reference`

`skin_reference()`

Everything the `skin` description takes: the anatomical zones (also usable by any paint layer as
{"zone": name}), the tone model, features, wrinkles, hair, scars, tattoos and make-up with their keys and
defaults.
