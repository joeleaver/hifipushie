# Hair: colour (the look keys, colour from a photo, Cycles)

Read guide(topic="hair") first: describe the hairstyle in words before touching a knob.

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
| sun_length | m (default 0.28): the hair's age from the scalp by which `sun` lightening is full. The FRONT view sees the first 2-10 cm of every strand, the back the lengths: at 0.28 the dome stays dark from the front while the back is light; e.g. 0.06 (with root 0.05: a little root darkness at the part) |
| tip_alpha, backscatter, scatter | 0..1 each (EEVEE strands; default 0 = off): the game hair shader's terms: see-through tips, warm light through thin / back-lit hair, a darker richer core with lighter outer layers (e.g. 0.5 / 0.6 / 0.8; checklist 11b, 11c) |
Also: eevee_sat / eevee_gain (how EEVEE draws the colour; e.g. 0.3 / 1.4), seen (the colour it should READ, e.g. from a
photo), grey_amount, cycles_* (Cycles only). Match by measure: look_hair measure "colour" (colour_bands + variation).

   **Colour from a photo: `look.seen`**, not `lit`. The colour keys are asked for the renderer, which gives back
   about a third of their saturation (Cycles' hair BSDF; EEVEE's strands copy that), so a photo's light brown typed
   into `lit` renders grey-blond. `seen` = the colour the hair should READ (the median of the photo's LIT hair, not
   its shadow side: the render makes its own shadows) derives lit / gap / sheen / tip / eevee_sat / the scalp tint
   (EEVEE then draws seen exactly; Cycles as much as the gamut allows). Colour keys given beside it still win.
   Measured once (flat frontal light): the rendered lit hair came out ~1.25x as saturated as seen: ask a little
   less. Hair against a warm wall in the photo looks ashier than the same numbers on our grey backdrop.
Cycles (look_hair(engine="cycles")): two look keys calibrate it against a reference, by measure (colour of the dense
hair's shadow / mid / highlight bands through the fitted camera under the fitted light):
`look.cycles_width` (x strand width for path-traced renders only: a 70k-strand groom at true hair width is a
see-through veil over the scalp; e.g. 1.8) and `look.cycles_sat` (the look colour's saturation kept: dense dark hair
comes out redder than asked; e.g. 0.65). EEVEE is untouched by both.
5. **Colour in Cycles.** The hair BSDF's colour is not what a lit mass of strands renders as: uncalibrated, a dark
   grey-brown came out 3.5-4x too light. The look colour goes through a measured inverse (`hair_strands.CYCLES_FIT`;
   `look.cycles_fit: [1, 1]` turns it off). Mid and light colours land within ~5-40% of `look.lit`; near-black
   can't go under the highlights' own floor. Judge colour on the Cycles look, shape on the EEVEE one.
6. Dark slits between layers of locks are the scalp's tint in shadow (`look.scalp_tint`, default 0.85, made for
   dark hair): on grey or fair hair lower it (0.3-0.5; a grey crop with receded temple corners 0.15: at 0.5 the bare
   corners read as dark patches).
