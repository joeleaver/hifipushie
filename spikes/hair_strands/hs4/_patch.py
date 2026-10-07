def patch(p, pairs):
    s = open(p).read()
    for a, b in pairs:
        assert s.count(a) == 1, (p, a, s.count(a))
        s = s.replace(a, b)
    open(p, 'w').write(s)


patch('src/hifipushie/server.py', [
    ('''missed, "band": m}: hair gathered over the head into a tie and a tail leaving it; set parting.side "none").''',
     '''missed, "band": m}: hair gathered over the head into a tie and a tail leaving it; set parting.side "none"),
      loose ({"length": m | {front, top, sides, back, nape}, "level": m from the head centre (a one-length cut ends
      there: about -0.10 the jaw, -0.17 the shoulders), "spacing": m between lock roots, "body": m the mass builds
      up, "lift": m of root volume, "stiff": 0 hangs .. 1 keeps its root direction, "out": 0 combed along the scalp
      .. 1 straight out of it, "back": 0..1 combed back over the crown, "messy", "uneven", "ends": + under / - out,
      "face": 1 = kept off the face, "fringe": {length, span deg, depth, sweep, level, stiff}}: hair grown all over
      the scalp that FALLS on the neck, shoulders and back (or stands: an afro is out 1 + stiff 1 + curl): a bob,
      loose waves, long straight hair, a fringe, a crop, tousled hair. guide(topic="hair") has recipes per style).'''),
])
patch('src/hifipushie/hair_guide.md', [
    ('''1. **Groom the shapes** as for any hair: hairline, volume, parting; loose hair as drawn clumps; tied hair with''',
     '''1. **Groom the shapes** as for any hair: hairline, parting; LOOSE hair with `groom.loose` (below); tied hair with'''),
    ('''## What went wrong on the way (so you can recognise it)
''', '''## Loose hair: `groom.loose`

Hair that grows all over the scalp, is combed some way at its roots, then falls (or stands). It replaces the
generated tiers; the parting and hairline still apply. It is kept off the head, neck, shoulders and clothes by the
body's own signed distance, so it lies on the shoulders and down the back, and off the face unless it is a fringe.

| key | what | typical |
|---|---|---|
| length | m of hair from the root; or per region `{front, top, sides, back, nape}` (a layered cut, a short back and sides) | 0.3 shoulder, 0.5 mid-back, 0.04 a crop |
| level | every lock is cut where it crosses this height, m from the head centre (about the brows): a one-length cut | -0.105 jaw (a bob), -0.17 shoulders |
| spacing | m between lock roots (lock width follows) | 0.02 long hair, 0.015 short |
| body, lift | m the mass builds up as locks come down over each other; m of root volume | 0.02, 0.006; curls 0.035, 0.012 |
| stiff | 0 hangs at once .. 1 keeps the direction it left the scalp in | 0.2-0.3 long, 0.6 short, 1 an afro |
| out | 0 combed along the scalp .. 1 straight out of it | 0; tousled 0.3; an afro 1 |
| back, messy, uneven | combed back over the crown; root directions turned at random; lengths differ | |
| ends | the ends turn under (+) or flick out (-) | a bob 0.5 |
| face | 1 = hair is turned aside where it would hang over the face (curtains beside the cheeks); 0 = it falls where it falls | 1 |
| fringe | `{length, span (deg either side), depth (m behind the hairline), sweep (-1..1), level, stiff}`: combed forward over the forehead | length 0.07, level -0.004 (the brows) |

The texture is the `strands` dials, not the groom:

| hair | groom.loose | strands |
|---|---|---|
| loose waves, shoulder length | length 0.3, body 0.024, stiff 0.3, uneven 0.5, spacing 0.021 | wave 0.014, wavelength 0.09, curl 0.25, clump 0.55, loose 0.45 |
| bob with a fringe | level -0.105, length 0.3, ends 0.6, uneven 0.15, parting none, fringe | wave 0.002, clump 0.4, flyaway 0.02, tips 0.15, taper 0.3 |
| long straight | length 0.5, stiff 0.2, messy 0.05, spacing 0.02, parting centre | wave 0.003, wavelength 0.16, clump 0.45, loose 0.2 |
| tight curls (ringlets) | length 0.22, body 0.035, lift 0.012, stiff 0.45, out 0.25 | wave 0.03, wavelength 0.028, curl 1, random 1, clump 0.85, clump_size 0.012, clump_shape 0.1 |
| afro (coils) | length 0.085, out 1, stiff 1, body 0, lift 0, spacing 0.02 | wave 0.03, wavelength 0.012, curl 1, random 1, clump 0.3, frizz 0.8, count 40000 |
| short tousled | length {front .05, top .055, sides .03, back .035, nape .018}, stiff 0.6, out 0.3, messy 0.7, spacing 0.015 | clump 0.4, tip_spread 0.7, loose 0.6, tips 0.8 |
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

## What went wrong on the way (so you can recognise it)

- Hair painted onto the face and shoulders like a stain: the collision proxy mesh was inside out (Shrinkwrap pulls
  what it takes for "inside" to the surface). `tests/test_hair_loose.py::test_collider_mesh_faces_out`.
- A curtain of hair over one eye, tufts standing along the parting: front hair has no direction from gravity (on
  the forehead it points over the face), and the mass was lifted at the roots. Hair is turned aside where it would
  hang in front of the face; the mass builds up as locks descend, not at their roots.
- Long hair fanned out over both arms: a lock lying on a shoulder kept its sideways direction. It slides off to
  the front or the back.
'''),
])
