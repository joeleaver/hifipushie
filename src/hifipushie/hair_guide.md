# Hair

Hair is not part of the SDF field: it lives in the model's Blender scene, so hair edits never rebuild the body.
Pick the path by the job:
- **Realistic hair** (the default for a realistic human): a STRAND groom on Blender's Hair Curves (`hair.style`
  "strands"). Tied back (ponytail, bun, plait, half up): `tie_hair` with a few style words. Loose: `groom_hair` with
  `groom.loose`. Short cuts: a baked cap + sparse cards. Judge in EEVEE (`look_hair`).
- **Stylised, feature-animation hair**: sculpted LOCKS, a few big designed shapes: guide(topic="hair_locks").
- **Game export**: cards cut from the strands (`export_hair` / `export_asset`).

Enable the tools with `enable_toolset("hair")`; the model needs its scene once (`sync`). Sub-topics
(guide(topic=...)): `hair_checklist` (the 15 rules that make hair read as hair: measure and knob for each),
`hair_tied` (`tie_hair`: every style word), `hair_loose` (`groom.loose`, recipes per hair type, existing sculpted
grooms as strands, laying a crop), `hair_short` (short cuts as a baked cap + cards), `hair_colour` (the look's colour
keys, colour from a photo, Cycles), `hair_export` (game cards, judging the export, engines, limits), `hair_tools`
(every hair tool's parameters), `hair_locks` (stylised), `hair_background` (practice, sources, engines).

**The rule everything else follows: describe the hairstyle in words from every reference view before touching a
knob.** Then groom from those sentences, one region at a time, and judge each region against its sentence. Numbers
don't see a style: a short cut combed ACROSS once read "brushed up and back" by every measure while the render was a
different haircut. When a groom is wrong, rewrite the description and rebuild from it; don't tune the last groom.

**Groom on the FINAL head.** The hair sits on the head that will ship. A groom made on an earlier head must be
re-seated and re-checked against the reference after any head change (hairline height, stand-off per region,
coverage, the part, the ears): `tie_hair(other, carry_from=name)` carries the style words and look, not a check.
Never carry a groom across heads, or re-tie one with defaults, without describing and judging it again.

## Stage 0: describe the hairstyle (before any groom)

From the front, three-quarter and profile references, write each item with what you see, a number where one can be
read (cm, against the brows, ears, shoulders), and which view shows it; mark items no view shows as inferred. Then
write the same list for YOUR render, then the differences.

1. **The style in one sentence**: e.g. "a low loose side ponytail, centre part, soft wisps at the temples", "a short
   back and sides, 5 cm on top combed across to his left, lying low".
2. **Hairline**: its curve, how far the temples recede, the front edge's height above the brows (cm), whether the
   visible edge is the hairline or hair lying over it, how thin the very front is, whether skin shows through; the
   temple corners and sideburns.
3. **Parting**: where, how deep, how much scalp shows (or none, or no part at all).
4. **Comb direction and lift by region** (front, top, sides, back, nape), as seen in each view: up / back / across /
   forward, flat or standing; how far the front stands off at the forelock in profile.
5. **Volume / stand-off per region**: how far the hair's outline stands off the skull (mm) over the top, sides, crown,
   above a tie. Real hair stands ~1.5-2 cm off the skull over the top and sides.
6. **Lengths** per region and how the ends sit (one length, layered, tapered nape, fringe length); for long hair, how
   it leaves the part and falls, what frames the face, what's tucked behind an ear or in front of the shoulders.
7. **Lock separation and texture**: one smooth mass, defined locks, waves (where, how big), curls, frizz, wisps,
   escaped hairs, halo at the silhouette.
8. **Colour**: the lit colour (sampled from the lit hair, not the shadow side), root vs lengths, the range front vs
   back, highlights, grey (where, how much).
9. **Coverage**: where scalp shows in the reference (usually only along the part line) and where it must not.

Then choose the path and the tool from the description (tied -> `tie_hair` words; loose -> `groom.loose` with a recipe
from `hair_loose`; a crop -> the short-cut path) and say which item justifies each choice. With fitted reference
cameras on the model (from the block-in), `hair_from_reference` measures stand-off, halo, hairline, parting and colour
from the pictures and writes a start; read its lines as measurements, not as the description.

## The stages

| # | Stage | Tools | Read first | Gate before going on |
|---|---|---|---|---|
| 0 | Describe | (words), `hair_from_reference` | `hair_checklist` (what to look for) | The description above, for the reference and for the current render |
| 1 | Shape | `tie_hair` / `groom_hair(groom=...)`, `look_hair(stage="mass")` | `hair_tied` (tied), `hair_loose` (loose: recipes per hair type), `hair_short` (crops) | Silhouette, stand-off per region, hairline, part, comb direction match the description from every side |
| 2 | Strands | `groom_hair(strands=...)` | `hair_checklist` ("Strand dials", rules 3-7, 12-15) | Lock separation, waves, halo, wisps match |
| 3 | Colour | `look` keys, `look.seen` | `hair_colour` | Colour bands and variation match (rules 8-11) |
| 4 | Export | `export_hair` / `export_asset` | `hair_export` | Each tier judged as an engine draws it |

Look after every change (`look_hair` takes 4-30 s); judge from every side (`views=["around"]`): tied hair is wrong
from behind first.

## Two principles every groom keeps

1. **Hair grows EVENLY over the growing area; parts are styling, not distribution.** Roots come from one even
   sampling of the hair-bearing scalp; a part, a sweep or a whorl is the COMB DIRECTION of strands from roots on both
   sides, never an absence of roots. No scalp shows outside the part line where the reference shows none. Knob:
   `strands.even` 1 (the default for loose long hair): every strand interpolated at its even root from the nearest
   lock guides (dense guides, `groom.loose.spacing` ~0.004; keep `part_soft.cross` 0 with even 1).
2. **Hair ARCS UP from the scalp, then falls.** Every strand leaves at an angle, rises by its root lift and the hair
   under it, turns and falls; the top's volume comes from that arc and it covers the scalp. Flat-from-the-root is a
   style choice (slicked, wet, tight), never the default. Knobs: loose hair `groom.loose.lift` from the measured
   stand-off (~1-1.5 cm on long hair), `out` 0.2-0.25 on the front / top, `stiff` ~0.35; tied hair `volume`.

## Craft rules (each once; measures and knobs in `hair_checklist`)

- Judge one region at a time against the reference in the SAME camera (`look_hair(views=["ref0", ...])`, the fitted
  cameras) or a fitted close-up; fix in checklist order: mass and stand-off, arcs from the part, locks with depth,
  halo, part, hairline, wisps, colour, highlights, gloss, tail, short-cut lay, strand fineness.
- The silhouette first (`stage: "mass"`): every later stage inherits it.
- Judge in EEVEE, and the export as the exported GLB re-imported into Blender EEVEE set up like a game (its own
  materials, alpha clip / hashed cards, no ray tracing). Cycles is never the judging render.
- A mass of LOCKS with depth, never one shell; under-layers darker.
- The hairline thins over ~1 cm with baby hairs; the temple is hair down to the ear. A hard edge reads as a wig.
- Short cuts are not long hair cut short: length and lay by region, combed one way per region, fine dense strands.
- Up-styles (high ponytail, top knot) and half up have no volume by default: hair pulled up doesn't fall from its
  roots.
- Colour from a photo goes in `look.seen` (the colour it should READ), not `lit`.
- EEVEE draws every strand at least a pixel wide: at a photo's scale render 2x and average down, with more strands,
  before judging fineness, texture or colour against a photo.
- Isolate a fault before fixing it: render with one piece off at a time (`look_hair(only=[...])`, a dial at 0).
- Tail and long-hair shape vary by seed (a tail's area about +-10%): judge over 3-4 seeds before trusting a change.
- Keep what worked: before a change you'd keep, re-render the styles you already accepted beside their accepted
  renders; a fix must not silently break them.

## Self-review loop (every round)

1. Render through the reference's fitted cameras (`ref0`, `ref1`, ...) and `views=["around"]`, plus close-ups of the
   hairline, both temples, the part and the back. Put each BESIDE the matching reference crop at the same framing.
2. Region by region (silhouette, top and part, hairline and temples, sides and ears, back and nape, lengths / tail,
   texture, colour) list what reads wrong against the reference, concretely (where, what, how far off). Mark each
   MAJOR (a different hairstyle, wrong silhouette or stand-off, wrong part or comb direction, scalp showing, a hard
   wig edge, a visible defect) or MINOR. Order: shape and form before texture, texture before colour.
3. Fix the worst MAJOR at its stage: usually the description and the shape, not a strand dial. Re-render.
4. Repeat until no region has a MAJOR. Re-check coverage every round: look from above, behind and the 3/4; no scalp
   off the part line.

A clean groom that isn't the reference's hairstyle is wrong. Numbers (IoU, stand-off) can match while the haircut
differs: the description decides. Argue a MAJOR away only with evidence that the reference doesn't show it.

## Common mistakes

| Mistake | Instead |
|---|---|
| Tuning dials on the last groom when the style is wrong | Rewrite the description and rebuild the groom from it |
| Judging from the front only | `views=["around"]` and the fitted reference cameras; the back first for tied hair |
| A combed cap hugging the skull ("flat") | Stand-off by region: `volume` (tied) / `lift`, `body` (loose) |
| A smooth helmet | Locks with depth: `volume.layers`, `volume.locks` (<= 0.4) |
| A hard dark hairline, a shaved temple | `hairline` soft, `wisps.baby`; the temple band is hair |
| Long-hair machinery on a crop (wavy noodles, wings, a curly back) | The short-cut recipe: lengths and lay by region, wave 0, fine dense strands |
| A clean notch of scalp at the part, scalp patches from above | Even roots (`strands.even` 1), soft part (`part_soft`), dense guides |
| Colour typed into `lit` from a photo (renders grey-blond) | `look.seen` |
| A groom carried or re-tied onto a changed head with defaults | Groom on the final head; after any head change re-seat, re-describe and re-judge (hairline, stand-off, coverage) |
| Judging the strands, shipping cards | `look_hair(tier=...)` / `export_hair(check=True)`: judge each tier as the engine draws it |

## Limits today

The head hair reads smoother than loose real hair in EEVEE; a tousled tail is stringier than brushed-out hair, with
few strays; single escaped hairs draw as thin lines (use wisps); the strip in front of the ear is thinner than real
hair; a crop's hairline density ramp is not yet soft enough. Cards are smoother than strands at bust distance, and
the far tier is a helmet. Details: guide(topic="hair_export").
