# Hair: loose hair (`groom.loose`) and sculpted grooms as strands

Read guide(topic="hair") first: describe the hairstyle in words before touching a knob.

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
the guides. Worked example: a short combed cut going grey, of 600+ thin hand locks, in this order:

1. `groom_hair(name, style="strands", strands={...})`. A short combed cut: `count` 100000, `clump` 0.3, `clump_size`
   0.006, `clump_shape` 0.5, `stray` 0.8, `loose` 0.4, `frizz` 0.2, `flyaway` 0.03, `tips` 0.6, `tip_spread` 0.5,
   `roots` 0.4, `under_length` 0.015, `wave` 0.003. Clump 0.4 with stray 0.6 at 60k strands read as strings.
2. **Grey.** A lock's own `grey` (0..1) is the SHARE of grey strands it grows, x `look.grey_locks` (default 1), plus
   `look.grey_amount` everywhere; `look.grey` is their colour. Locks made for the solid look often carry 0.35+
   everywhere: at grey_locks 1 the head is striped white. 0.6 was salt and pepper. The card tiers draw the same
   share (the locks' mean) in their pictures. The groom's DEFAULT temple / sideburn grey (`groom.grey` unset)
   follows the model's age: none to 30, all of it from 50 (`hair.grey_age`; a young head got grey streaks).
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
   can't go under the highlights' own floor. Judge shape and colour in EEVEE (the export's look); Cycles is for reference only.
6. Dark slits between layers of locks are the scalp's tint in shadow (`look.scalp_tint`, default 0.85, made for
   dark hair): on grey or fair hair lower it (0.3-0.5; a grey crop with receded temple corners 0.15: at 0.5 the bare
   corners read as dark patches).

### Laying a crop: `groom.loose.lay`

A short cut's height is not its length. Measured on a crop: `stiff` 0.6 on top stands it up as a brush
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
